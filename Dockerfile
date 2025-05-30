# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies that might be needed by some Python packages
# Example: build-essential for packages that compile from source
# You might need to add others depending on your specific dependencies
# RUN apt-get update && apt-get install -y build-essential

# Copy the requirements file into the container
COPY requirements.txt .

# Install Python dependencies
RUN pip install -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Expose the port the app runs on (adjust if your app runs on a different port internally)
# Uvicorn will run on port 8000 by default if not specified, or 80 as in the CMD below.
EXPOSE 80

# Command to run the application
# We use 0.0.0.0 to make the app accessible from outside the container within the Docker network/ECS/EKS
# For production, you might remove --reload and adjust workers as needed.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "80"]

RUN python -m nltk.downloader punkt averaged_perceptron_tagger 