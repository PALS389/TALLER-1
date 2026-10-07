# Viewer Dependencies

Locally served, pinned distribution files from npm through jsDelivr:

- Three.js 0.128.0: `three.min.js`, `OrbitControls.js`, `GLTFLoader.js`.
  This is the version used in Bray's EN-42 viewer delivery.
- Lucide 0.468.0: `lucide.min.js`, used for presentation controls.

The viewer adapts EN-42's scene, material, clipping and camera controls; binary
study artifacts are retrieved through the application's API module. No CDN
connection is required when viewing an existing study.
