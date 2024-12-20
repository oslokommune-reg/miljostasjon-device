# Use an official Python runtime as a parent image
FROM python:3.11

RUN apt-get update && apt-get install ffmpeg libsm6 libxext6  -y

# Set the working directory in the container
WORKDIR /usr/src/app

# Copy the current directory contents into the container at /usr/src/app
COPY ./main /usr/src/app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Define environment variable
ENV NAME dev

# Set the timezone
ENV TZ=Europe/Oslo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Run app.py when the container launches
# CMD ["python", "main.py"]
