# Godot Capture

Screenshot and video capture for Godot projects on Windows.

The Godot project is the working directory. All paths below are relative to it.

## Screenshot Capture

Screenshots go in `screenshots/` (gitignored). Each capture gets a subfolder.

```bash
MOVIE=screenshots/{folder}
rm -rf $MOVIE && mkdir -p $MOVIE
touch screenshots/.gdignore
godot --write-movie $MOVIE/frame.png \
    --fixed-fps 10 --quit-after {N} \
    --script test/test_task.gd 2>&1
```

Use a descriptive subfolder name (e.g., `player_movement`, `terrain_gen`). Use lowercase with underscores.

### Frame Rate and Duration

`--quit-after {N}` is the frame count. Choose based on scene type:
- **Static scenes** (decoration, terrain, UI): `--fixed-fps 1`. Adjust `--quit-after` for however many views needed (e.g. 8 frames for a camera orbit).
- **Dynamic scenes** (physics, movement, gameplay): `--fixed-fps 10`. Low FPS breaks physics — `delta` becomes too large, causing tunneling and erratic behavior. Typical: 3-10s (30-100 frames).

## Video Capture

```bash
VIDEO=screenshots/presentation
rm -rf $VIDEO && mkdir -p $VIDEO
touch screenshots/.gdignore
godot --write-movie $VIDEO/output.avi \
    --fixed-fps 30 --quit-after 900 \
    --script test/presentation.gd 2>&1
# Convert AVI (MJPEG) to MP4 (H.264)
ffmpeg -i $VIDEO/output.avi \
    -c:v libx264 -pix_fmt yuv420p -crf 28 -preset slow \
    -vf "scale='min(1280,iw)':-2" \
    -movflags +faststart \
    $VIDEO/gameplay.mp4 2>&1
```

**AVI to MP4:** Godot outputs MJPEG AVI. ffmpeg converts to H.264 MP4. CRF 28 + `-preset slow` targets ~2-5MB for a 30s clip at 720p.
