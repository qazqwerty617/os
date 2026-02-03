# Use official lightweight Python image
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies (gcc needed for some python libs)
RUN apt-get update && apt-get install -y \
    gcc \
    procps \
    lsof \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create necessary directories for data persistence
RUN mkdir -p journal_data learning_data

# Expose Dashboard Port
EXPOSE 8080

# Make start script executable
RUN chmod +x start.sh

# Run the bot
CMD ["./start.sh"]
