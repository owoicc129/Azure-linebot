from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    TextSendMessage,
    FlexSendMessage
)
import os
from imgur_python import Imgur
import sys
import time
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import json
import requests
from azure.cognitiveservices.vision.face import FaceClient
from msrest.authentication import CognitiveServicesCredentials
from azure.cognitiveservices.vision.face.models import TrainingStatusType
from azure.cognitiveservices.vision.computervision import ComputerVisionClient
from azure.cognitiveservices.vision.computervision.models import OperationStatusCodes



#Line
LINE_SECRET = os.getenv("secert")
LINE_TOKEN = os.getenv("token")
LINE_BOT = LineBotApi(LINE_TOKEN)
HANDLER = WebhookHandler(LINE_SECRET)

#Azure
KEY = os.getenv("Azure_face_key") 
ENDPOINT = os.getenv("Azure_face_Endpoint")  
FACE_CLIENT = FaceClient(ENDPOINT, CognitiveServicesCredentials(KEY))

#Imgur
IMGUR_CONFIG = {
  "client_id": os.getenv("imgur_client_id"),
  "client_secret": os.getenv("imgur_client_secret"),
  "access_token": os.getenv("imgur_access_token"),
  "refresh_token": os.getenv("imgur_refresh_token")
}
IMGUR_CLIENT = Imgur(config=IMGUR_CONFIG)



app = Flask(__name__)


@app.route('/')
def hello():
    return "hello world!"



@app.route("/callback", methods=["POST"])
def callback():
    # X-Line-Signature: 數位簽章
    signature = request.headers["X-Line-Signature"]
    print(signature)
    body = request.get_data(as_text=True)
    print(body)
    try:
        HANDLER.handle(body, signature)
    except InvalidSignatureError:
        print("Check the channel secret/access token.")
        abort(400)
    return "OK"
    
# message 可以針對收到的訊息種類
@HANDLER.add(MessageEvent, message=TextMessage)
def handle_message(event):
    url_dict = {
      "TIBAME":"https://www.tibame.com/coursegoodjob/traffic_cli", 
      "HELP":"https://developers.line.biz/zh-hant/docs/messaging-api/"}
# 將要發出去的文字變成TextSendMessage
    try:
        url = url_dict[event.message.text.upper()]
        message = TextSendMessage(text=url)
    except:
        message = TextSendMessage(text=event.message.text)
# 回覆訊息
    LINE_BOT.reply_message(event.reply_token, message)
    
    
#-------------------------------------------

@HANDLER.add(MessageEvent, message=ImageMessage)
def handle_content_message(event):
    # 先把傳來的照片存檔
    filename = "{}.jpg".format(event.message.id)
    message_content = LINE_BOT.get_message_content(
      event.message.id)
    with open(filename, "wb") as f_w:
        for chunk in message_content.iter_content():
            f_w.write(chunk)
    f_w.close()

    # 將取得照片的網路連結
    image = IMGUR_CLIENT.image_upload(filename, "", "")
    link = image["response"]["data"]["link"]
    
    # 回覆訊息[test]
    LINE_BOT.reply_message(event.reply_token, link)
    
    
    
    
    
    
    
if __name__=='__main__':
    app.run()
    
