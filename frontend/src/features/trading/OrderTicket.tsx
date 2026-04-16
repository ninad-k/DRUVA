import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { InstrumentSearch } from "@/components/layout/InstrumentSearch";
import { placeOrder } from "@/api/rest/endpoints";
import { useAccountStore } from "@/store/account";
import type { OrderType, OrderSide, ProductType } from "@/types/api";
import { cn } from "@/utils/cn";

const schema = z.object({
  symbol: z.string().min(1, "Required"),
  exchange: z.string().min(1, "Required"),
  side: z.enum(["BUY", "SELL"]),
  quantity: z.coerce.number().int().positive("Must be positive"),
  order_type: z.enum(["MARKET", "LIMIT", "SL", "SL-M"]),
  product: z.enum(["MIS", "CNC", "NRML"]),
  price: z.coerce.number().optional(),
  trigger_price: z.coerce.number().optional(),
});
type FormValues = z.infer<typeof schema>;

interface OrderTicketProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  defaults?: Partial<FormValues>;
}

export function OrderTicket({ open, onOpenChange, defaults }: OrderTicketProps) {
  const accountId = useAccountStore((s) => s.activeAccountId);
  const qc = useQueryClient();
  const [side, setSide] = useState<OrderSide>(defaults?.side ?? "BUY");

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      symbol: defaults?.symbol ?? "",
      exchange: defaults?.exchange ?? "NSE",
      side: defaults?.side ?? "BUY",
      quantity: defaults?.quantity ?? 1,
      order_type: defaults?.order_type ?? "MARKET",
      product: defaults?.product ?? "MIS",
      price: defaults?.price,
      trigger_price: defaults?.trigger_price,
    },
  });

  const orderType = watch("order_type") as OrderType;
  const product = watch("product") as ProductType;

  const mut = useMutation({
    mutationFn: async (values: FormValues) => {
      if (!accountId) throw new Error("No account selected");
      return placeOrder({ ...values, account_id: accountId, side });
    },
    onSuccess: () => {
      toast.success("Order placed");
      qc.invalidateQueries({ queryKey: ["orders"] });
      qc.invalidateQueries({ queryKey: ["dashboard-orders"] });
      onOpenChange(false);
      reset();
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { detail?: string } }; message?: string })?.response?.data
          ?.detail ?? (err as Error)?.message ?? "Failed to place order";
      toast.error(msg);
    },
  });

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Place Order</SheetTitle>
          <SheetDescription>
            {accountId ? `Account: ${accountId.slice(0, 8)}…` : "No account selected — connect one first."}
          </SheetDescription>
        </SheetHeader>

        <form
          onSubmit={handleSubmit((v) => mut.mutate(v))}
          className="space-y-4"
        >
          <div className="space-y-1.5">
            <Label>Instrument</Label>
            <InstrumentSearch
              onSelect={(sym, exch) => {
                setValue("symbol", sym, { shouldValidate: true });
                setValue("exchange", exch, { shouldValidate: true });
              }}
            />
            <Input
              placeholder="e.g. RELIANCE"
              {...register("symbol")}
              className="mt-1"
            />
            {errors.symbol && (
              <p className="text-xs text-[hsl(var(--loss))]">{errors.symbol.message}</p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2">
            <Button
              type="button"
              variant={side === "BUY" ? "default" : "outline"}
              onClick={() => setSide("BUY")}
              className={cn(side === "BUY" && "bg-[hsl(var(--gain))] hover:bg-[hsl(var(--gain))]/90 text-white")}
            >
              Buy
            </Button>
            <Button
              type="button"
              variant={side === "SELL" ? "default" : "outline"}
              onClick={() => setSide("SELL")}
              className={cn(side === "SELL" && "bg-[hsl(var(--loss))] hover:bg-[hsl(var(--loss))]/90 text-white")}
            >
              Sell
            </Button>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="quantity">Quantity</Label>
              <Input id="quantity" type="number" min="1" {...register("quantity")} />
              {errors.quantity && (
                <p className="text-xs text-[hsl(var(--loss))]">{errors.quantity.message}</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label>Product</Label>
              <Select
                value={product}
                onValueChange={(v) => setValue("product", v as ProductType)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="MIS">MIS (Intraday)</SelectItem>
                  <SelectItem value="CNC">CNC (Delivery)</SelectItem>
                  <SelectItem value="NRML">NRML (Carryforward)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>Order Type</Label>
            <Select
              value={orderType}
              onValueChange={(v) => setValue("order_type", v as OrderType)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="MARKET">Market</SelectItem>
                <SelectItem value="LIMIT">Limit</SelectItem>
                <SelectItem value="SL">SL</SelectItem>
                <SelectItem value="SL-M">SL-M</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {(orderType === "LIMIT" || orderType === "SL") && (
            <div className="space-y-1.5">
              <Label htmlFor="price">Price</Label>
              <Input id="price" type="number" step="0.05" {...register("price")} />
            </div>
          )}

          {(orderType === "SL" || orderType === "SL-M") && (
            <div className="space-y-1.5">
              <Label htmlFor="trigger_price">Trigger price</Label>
              <Input id="trigger_price" type="number" step="0.05" {...register("trigger_price")} />
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={mut.isPending || !accountId}>
              {mut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Place {side}
            </Button>
          </div>
        </form>
      </SheetContent>
    </Sheet>
  );
}
