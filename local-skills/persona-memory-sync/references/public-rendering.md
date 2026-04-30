# Public Rendering

## Boundary Note

This document only governs how the current `persona-memory-sync` skill renders existing public-safe fields.

It does not authorize adding new product responsibilities, new rendering products, recommendation flows,
notification flows, or any new business workflow beyond the current persona write/sync/render scope.

Public rendering must never expose raw internal matcher labels.

Examples:

- raw: `绿茶`
  public: `关系边界需要进一步确认`
- raw: `拜金`
  public: `消费观建议重点确认`
- raw: `冷暴力`
  public: `沟通方式建议重点确认`
- raw: `暧昧不清`
  public: `认真交往意愿需进一步确认`

Preferred flow:

1. normalize raw labels into internal matcher features
2. write matcher features into `profiles.matcher_*`
3. render public-safe text into `profiles.public_*`
