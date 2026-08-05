#!/bin/bash
# dispatcher-run-t_* topic'lerini default-instance base_dir'inden arşive taşı (silme YOK, geri alınabilir).
# Kullanım: archive_dispatcher_run_topics.sh [--dry-run]
set -euo pipefail
BASE=/home/user/CLEANUP/DATA/Wiki-BASE
ARC=/home/user/CLEANUP/DATA/Wiki-ARCHIVE/dispatcher-run-topics
DRY=${1:-}
moved=0
for layer_dir in "$BASE"/*/; do
    layer=$(basename "$layer_dir")
    for f in "$layer_dir"dispatcher-run-t_*.md; do
        [ -e "$f" ] || continue
        if [ "$DRY" = "--dry-run" ]; then
            echo "WOULD MOVE: $layer/$(basename "$f")"
        else
            mkdir -p "$ARC/$layer"
            mv "$f" "$ARC/$layer/"
        fi
        moved=$((moved+1))
    done
done
echo "TOPLAM: $moved dosya ($([ "$DRY" = "--dry-run" ] && echo dry-run || echo taşındı))"
[ "$moved" -gt 0 ] || { echo "hiç dispatcher-run dosyası yok"; exit 0; }
