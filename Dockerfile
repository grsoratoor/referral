FROM python:3.10 AS labels
LABEL maintainer="https://t.me/hackspider"
LABEL description="A customizable, multilanguage Telegram referral bot"

FROM labels AS dependencies
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

FROM dependencies AS referral
COPY . /usr/src/referral
WORKDIR /usr/src/referral

FROM referral AS entry
ENTRYPOINT ["python"]
CMD ["main.py"]

FROM entry AS environment
ENV PYTHONUNBUFFERED=1
ENV CONFIG_PATH="/etc/referral/config.toml"
ENV DB_ENGINE="sqlite:////var/lib/referral/database.sqlite"