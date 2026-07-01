#!/bin/bash
set -e

cd "$(dirname "$0")"

source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate benchmark_web_2

python manage.py migrate --run-syncdb
python manage.py runserver 0.0.0.0:8001
