#!/usr/bin/env bash
# inspect.sh VIDEO [COLS] - check a rendered video without watching it.
# Writes <video>_sheet.png (one frame every ~2 s, tiled) and prints size, duration,
# audio presence and loudness. Read the PNG to judge framing, captions, and moods.
set -euo pipefail
v="${1:?usage: inspect.sh VIDEO [COLS]}"; cols="${2:-4}"
[[ -s "$v" ]] || { echo "inspect.sh: no such video: $v" >&2; exit 1; }
dur="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$v")"
size="$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$v")"
audio="$(ffprobe -v error -select_streams a -show_entries stream=codec_name -of csv=p=0 "$v" | head -1)"
frames=$(( cols * 2 ))
step="$(awk -v d="$dur" -v n="$frames" 'BEGIN{s=d/n; printf "%.3f", (s<0.5?0.5:s)}')"
w=$(( 1280 / cols ))
sheet="${v%.*}_sheet.png"
ffmpeg -loglevel error -y -i "$v" -vf "fps=1/$step,scale=$w:-1,tile=${cols}x2" -frames:v 1 "$sheet"
echo "video:    $v"
echo "size:     $size, ${dur%.*}s ($(printf '%.1f' "$dur") s)"
if [[ -n "$audio" ]]; then
  ffmpeg -nostats -i "$v" -af volumedetect -f null - 2>&1 \
    | sed -nE 's/.*(mean_volume|max_volume): (.*)/\1: \2/p' | sed 's/^/audio:    /'
else
  echo "audio:    NONE (no audio stream)"
fi
echo "sheet:    $sheet (every ${step}s)"
