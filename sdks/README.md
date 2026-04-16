# DHRUVA Multi-Language SDKs

Generated clients for the DHRUVA gRPC API in six languages. The proto contracts
live in [`/proto`](../proto) (single source of truth).

## Generate locally

```bash
# install once
brew install bufbuild/buf/buf            # macOS
# or: curl -fsSL https://github.com/bufbuild/buf/releases/latest/download/buf-Linux-x86_64.tar.gz | tar xz

# generate everything from /proto
cd sdks
buf generate ../proto
```

## Per-language output

| Language | Path | Build / publish |
|---|---|---|
| Python | `sdks/python/` | `pip install -e .` then `twine upload` |
| TypeScript | `sdks/typescript/` | `npm publish` (Connect-Web compatible) |
| Java | `sdks/java/` | Maven/Gradle to Sonatype |
| Go | `sdks/go/` | tag + `go install` |
| C# / .NET | `sdks/csharp/` | NuGet pack + push |
| Rust | `sdks/rust/` | `cargo publish` |

## CI

GitHub Actions workflow (`.github/workflows/sdks.yml`) regenerates and
publishes on every `v*` tag. SDKs are versioned with the same semver as the
backend.

## Why six languages

DHRUVA's gRPC contracts make per-language clients almost free. We mirror
OpenAlgo's six-language SDK matrix — Python (most strategy authors), Node
(JS-first shops), Java (institutions), Go (HFT-adjacent stacks),
C#/.NET (windows desktop tooling, Excel add-ins), Rust (low-latency
adapters and embedded use cases).
