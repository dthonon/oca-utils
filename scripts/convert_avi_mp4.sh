
#!/bin/bash

# Usage, inside directory containing AVI: ./convert_apv_mp4.sh

trap "echo Fin; exit" SIGINT SIGTERM

for f in *.AVI; do
    prise=$(date --iso-8601=second -r $f)
    ffmpeg -i "$f" -map_metadata 0:s:0 -metadata creation_time="$prise" ${f/%AVI/mp4}
    touch --no-create --reference="$f" ${f/%AVI/mp4}
done
