#!/etc/profiles/per-user/h3x/bin/bash

rsync -av /mnt/data/projects/h3xrecon/build/Processor recon:/home/h3x/h3xrecon/ --exclude=.git --exclude="**/__pycache__/*" --exclude=venv

#rsync -av /mnt/data/projects/h3xrecon_v2/ vps4:/home/ubuntu/h3xrecon_v2/ --exclude=.git --exclude="**/__pycache__/*" --exclude=venv