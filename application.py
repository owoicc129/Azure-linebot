from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    ImageMessage,
    TextMessage,
    TextSendMessage,
    FlexSendMessage
)
import os
from imgur_python import Imgur
import sys
import time
from datetime import datetime, timezone, timedelta
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import json
import requests
import re
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

#Azure ORC
SUBSCRIPTION_KEY = os.getenv("Azure_ORC_sUBSCRIPTION_KEY")
ENDPOINT = os.getenv("Azure_ORC_ENDPOINT")
CV_CLIENT = ComputerVisionClient(
    ENDPOINT, CognitiveServicesCredentials(SUBSCRIPTION_KEY)
)

#Imgur
IMGUR_CONFIG = {
  "client_id": os.getenv("imgur_client_id"),
  "client_secret": os.getenv("imgur_client_secret"),
  "access_token": os.getenv("imgur_access_token"),
  "refresh_token": os.getenv("imgur_refresh_token")
}
IMGUR_CLIENT = Imgur(config=IMGUR_CONFIG)


#--def----------------------------------------------------

def azure_face_recognition(filename):
    PERSON_GROUP_ID = "tibame1"

    img = open(filename, "r+b")
    detected_face = FACE_CLIENT.face.detect_with_stream(img, detection_model="detection_01")
    # 多於一張臉的情況
    if len(detected_face) != 1:
        return ""
    results = FACE_CLIENT.face.identify([detected_face[0].face_id], PERSON_GROUP_ID)
    # 沒有結果的情況
    if len(results) == 0:
        return "unknown"

    result = results[0].as_dict()
    # 找不到相像的人
    if len(result["candidates"]) == 0:
        return "unknown"
    # 雖然有類似的人，但信心程度太低
    if result["candidates"][0]["confidence"] < 0.5:
        return "unknown"
        
    person = FACE_CLIENT.person_group_person.get(PERSON_GROUP_ID, result["candidates"][0]["person_id"])
    return person.name


def azure_ocr(url):

    ocr_results = CV_CLIENT.read(url, raw=True)
    operation_location_remote = ocr_results.headers["Operation-Location"]
    operation_id = operation_location_remote.split("/")[-1]
    status = ["notStarted", "running"]
    while True:
        get_handw_text_results = CV_CLIENT.get_read_result(operation_id)
        if get_handw_text_results.status not in status:
            break
        time.sleep(1)

    text = []
    succeeded = OperationStatusCodes.succeeded
    if get_handw_text_results.status == succeeded:
        res = get_handw_text_results.analyze_result.read_results
        for text_result in res:
            for line in text_result.lines:
                if len(line.text) <= 8:
                    text.append(line.text)

    # 利用 Regular Expresion (正規表示法) 針對台灣車牌的規則過濾
    r = re.compile("[0-9A-Z]{2,4}[.-]{1}[0-9A-Z]{2,4}")
    text = list(filter(r.match, text))
    return text[0].replace(".", "-") if len(text) > 0 else ""


def azure_object_detection(url, filename):
    img = Image.open(filename)
    draw = ImageDraw.Draw(img)
    font_size = int(5e-2 * img.size[1])
    fnt = ImageFont.truetype(
      "static/TaipeiSansTCBeta-Regular.ttf", size=font_size)
    object_detection = CV_CLIENT.detect_objects(url)
    if len(object_detection.objects) > 0:
        for obj in object_detection.objects:
            left = obj.rectangle.x
            top = obj.rectangle.y
            right = obj.rectangle.x + obj.rectangle.w
            bot = obj.rectangle.y + obj.rectangle.h
            name = obj.object_property
            confidence = obj.confidence

            # 畫框並標上物件名稱與信心程度
            draw.rectangle([left, top, right, bot], outline=(255, 0, 0), width=3)
            draw.text([left, top + font_size],"{} {}".format(name, confidence),fill=(255, 0, 0),font=fnt)

    # 把畫完的結果存檔，利用 imgur 把檔案轉成網路連結
    img.save(filename)
    image = IMGUR_CLIENT.image_upload(filename, "", "")
    link = image["response"]["data"]["link"]
    # 最後刪掉圖檔
    os.remove(filename)
    return link


def azure_describe(url):
    description_results = CV_CLIENT.describe_image(url)
    output = ""
    for caption in description_results.captions:
        output += "'{}' with confidence {:.2f}% \n".format(
            caption.text, caption.confidence * 100
        )
    return output



#--linebot-------------------------------

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
        LINE_BOT.reply_message(event.reply_token, message)

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
    
    
    name = azure_face_recognition(filename)
    if name != "": # 如果只有一張人臉，輸出人臉辨識結果
        now = datetime.now(timezone(timedelta(hours=8))).\
        strftime("%Y-%m-%d %H:%M") # 注意時區
        output = "{0}, {1}".format(name, now)
        
    else:
        plate = azure_ocr(link)
        link_ob = azure_object_detection(link, filename)
        # 有車牌就輸出車牌
        if len(plate) > 0:
            output = "License Plate: {}".format(plate)
        # # 沒有車牌就就輸出影像描述的結果
        else:
            output = azure_describe(link)
        link = link_ob
    

    with open("templates/result.json", "r") as f_r:
        bubble = json.load(f_r)
    f_r.close()
    # bubble["body"]["contents"][0]["contents"][0]["contents"][0]["text"] = output
    # bubble["header"]["contents"][0]["contents"][0]["contents"][0]["url"] = link
    bubble["body"]["contents"][0]["contents"][0]['url'] = link
    bubble["body"]["contents"][1]["contents"][0]["contents"][0]["contents"][2]['text']= output

    LINE_BOT.reply_message(
        event.reply_token, [FlexSendMessage(alt_text="Report", contents=bubble)]
    )


    
    # 回覆訊息
    LINE_BOT.reply_message(event.reply_token, TextSendMessage(text=output))
    
    
    
    
    
    
    
if __name__=='__main__':
    app.run()
    
