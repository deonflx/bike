#!/usr/bin/env bash
# build.sh — Render build script for GeoDjango
# Render runs this during every deploy

set -o errexit  # exit on error

# 1. Install GDAL, GEOS, PROJ (GeoDjango system dependencies)
apt-get update && apt-get install -y \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    proj-bin \
    libproj-dev

# 2. Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 3. Collect static files (served by Whitenoise)
python manage.py collectstatic --no-input

# 4. Run database migrations
python manage.py migrate --no-input
