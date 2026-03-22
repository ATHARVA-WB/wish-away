#base image
FROM python:3.12

#set working directory
WORKDIR /app

#copy project files
COPY . /app

#install dependencies
RUN pip install --no-cache-dir -r requirements.txt

#expose flask port
EXPOSE 5000

#run the application
CMD ["python", "app.py"]