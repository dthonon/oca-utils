
#!/bin/bash

# Usage, inside directory containing AVI: ./convert_apv_mp4.sh

trap "echo Fin; exit" SIGINT SIGTERM

for f in ${1-*.AVI}; do
    g=${f/%AVI/mp4}
    prise=$(date --iso-8601=second -r $f)
    echo "Conversion MP4 de $f en $g"
    ffmpeg -y -hwaccel cuda -hwaccel_output_format cuda -i "$f" \
        -map_metadata 0:s:0 -metadata creation_time="$prise" -c:v h264_nvenc $g
    touch --no-create --reference="$f" $g
done
