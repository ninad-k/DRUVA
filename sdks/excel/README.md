# DHRUVA Excel Integration

Two modes are supported:

1. **Office Scripts / VBA macros** that call the DHRUVA REST API. Works with
   any Excel install; no add-in required.
2. **Excel Web Add-in** (manifest under `manifest.xml`). Drop into the Excel
   Office Add-in upload pane to surface a sidebar with one-click order
   placement.

## Setup

Generate a long-lived API token via the REST API:

```bash
curl -X POST https://your-dhruva.example.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"...","password":"..."}'
```

Take the `access_token` and store it in **Excel → File → Options →
Customize Ribbon → DHRUVA → Token**, or set the env-var on the machine that
runs the macro.

## Office Script (TypeScript) example

```ts
async function placeOrder(workbook: ExcelScript.Workbook) {
  const token = "PASTE_DHRUVA_ACCESS_TOKEN_HERE";
  const sheet = workbook.getActiveWorksheet();
  const account = sheet.getRange("B1").getValue() as string;
  const symbol  = sheet.getRange("B2").getValue() as string;
  const side    = sheet.getRange("B3").getValue() as string;
  const qty     = sheet.getRange("B4").getValue() as number;

  const response = await fetch("https://your-dhruva.example.com/api/v1/orders", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      account_id: account,
      symbol,
      exchange: "NSE",
      side,
      quantity: qty,
      order_type: "MARKET",
      product: "MIS",
    }),
  });
  sheet.getRange("B6").setValue(await response.text());
}
```

## VBA example (legacy Excel)

```vb
Sub PlaceOrder()
    Dim http As Object: Set http = CreateObject("MSXML2.XMLHTTP")
    http.Open "POST", "https://your-dhruva.example.com/api/v1/orders", False
    http.setRequestHeader "Authorization", "Bearer " & Range("B1").Value
    http.setRequestHeader "Content-Type", "application/json"
    http.send "{""account_id"":""" & Range("B2").Value & _
              """,""symbol"":""" & Range("B3").Value & _
              """,""exchange"":""NSE"",""side"":""" & Range("B4").Value & _
              """,""quantity"":" & Range("B5").Value & _
              ",""order_type"":""MARKET"",""product"":""MIS""}"
    Range("B7").Value = http.responseText
End Sub
```

## Web Add-in manifest

`manifest.xml` is a minimal Office Add-in descriptor pointing at a tiny
React panel hosted at `https://your-dhruva.example.com/excel-addin/`. Build
the panel from `frontend/src/features/excel-addin/` (skeleton in this repo).

## Google Sheets

Use Google Apps Script with `UrlFetchApp.fetch`:

```javascript
function placeOrder() {
  const token = PropertiesService.getScriptProperties().getProperty('DHRUVA_TOKEN');
  const sheet = SpreadsheetApp.getActiveSheet();
  const payload = {
    account_id: sheet.getRange('B1').getValue(),
    symbol: sheet.getRange('B2').getValue(),
    exchange: 'NSE',
    side: sheet.getRange('B3').getValue(),
    quantity: sheet.getRange('B4').getValue(),
    order_type: 'MARKET',
    product: 'MIS',
  };
  const response = UrlFetchApp.fetch('https://your-dhruva.example.com/api/v1/orders', {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + token },
    payload: JSON.stringify(payload),
  });
  sheet.getRange('B6').setValue(response.getContentText());
}
```

Set `DHRUVA_TOKEN` once via Apps Script editor → File → Project properties.

## Templates

- `templates/positions.xlsx` — pulls live positions via `=WEBSERVICE("https://.../api/v1/positions?...")`. Refreshes every 60s by default.
- `templates/strategy-blotter.xlsx` — strategy P&L pivot.

(Templates are shipped separately; this folder is the reference glue code.)
