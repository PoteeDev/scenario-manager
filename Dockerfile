FROM python:3.10-alpine
WORKDIR /usr/app/
COPY requirements.txt .
RUN pip3 install -r requirements.txt
COPY manager .
CMD [ "python3", "server.py" ]