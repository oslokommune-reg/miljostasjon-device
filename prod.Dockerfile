# Use an official Python runtime as a parent image
FROM python:3.11

RUN apt-get update && apt-get install ffmpeg libsm6 libxext6 -y && \
    GTHREAD=$(find /usr/lib -name 'libgthread-2.0.so.0.*' -not -type l | head -1) && \
    GLIB=$(find /usr/lib -name 'libglib-2.0.so.0.*' -not -type l | head -1) && \
    if [ -n "$GTHREAD" ] && [ ! -s "$GTHREAD" ] && [ -n "$GLIB" ]; then \
        ln -sf "$GLIB" "$GTHREAD"; \
        echo "Patched empty libgthread stub -> $GLIB"; \
    fi

# Set the working directory in the container
WORKDIR /usr/src/app

# Install packages before copying the code, so a code-only change reuses
# the cached pip layer: rebuilds take seconds instead of minutes, which
# matters in 10-minute power windows and saves SD card writes.
COPY ./main/requirements.txt /usr/src/app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY ./main /usr/src/app

# Define environment variable
ENV NAME prod

# Set the timezone
ENV TZ=Europe/Oslo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Run app.py when the container launches
# CMD ["python", "main.py"]
