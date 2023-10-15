
#!/bin/bash

# Usage, inside directory containing AVI: ./convert_apv_mp4.sh

for f in *.AVI; do 
    ffmpeg -i "$f" ${f/%AVI/mp4};
    touch -d "$(date -R -r "$f")" ${f/%AVI/mp4}
done