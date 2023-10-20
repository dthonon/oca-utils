
#!/bin/bash

# Usage, inside directory containing AVI: ./convert_apv_mp4.sh

trap "echo Fin; exit" SIGINT SIGTERM

for f in ${1-*.AVI}; do
    g=${f/%AVI/mp4}
    prise=$(date --iso-8601=second -r $f)
    echo "Conversion MP4 de $f en $g"
    ffmpeg -y -hwaccel cuda -hwaccel_output_format cuda -i "$f" \
        -map_metadata 0:s:0 -metadata creation_time="$prise" -vf scale_cuda=1280:720 -c:v h264_nvenc \
        -fps_mode passthrough -preset p7 -tune hq -b:v 35M -bufsize 50M -maxrate 50M -qmin 0 -g 250 \
        -bf 3 -b_ref_mode middle -temporal-aq 1 -rc-lookahead 20 -i_qfactor 0.75 -b_qfactor 1.1 $g
    touch --no-create --reference="$f" $g
done
