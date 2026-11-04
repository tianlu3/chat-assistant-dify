import os
import time
import hashlib
import requests
from flask import Flask, request, make_response
import xml.etree.ElementTree as ET
from wechatpy.crypto import WeChatCrypto

app = Flask(__name__)

# ========== 配置区域：请务必修改！ ==========
APP_ID = os.getenv('WECHAT_APP_ID', 'your-app-id')
APP_SECRET = os.getenv('WECHAT_APP_SECRET', 'your-app-secret')
TOKEN = os.getenv('WECHAT_TOKEN', 'dify123456')  # 必须与公众号后台配置完全一致
ENCODING_AES_KEY = os.getenv('WECHAT_AES_KEY', '')  # 如果选明文模式，这里留空！

DIFY_API_KEY = os.getenv('DIFY_API_KEY', 'app-your-key')
DIFY_WORKFLOW_URL = os.getenv('DIFY_WORKFLOW_URL', 'http://127.0.0.1/v1/workflows/run')

HOST = '0.0.0.0'
PORT = 8080  # 建议改成 8080，因为 80 可能被占用


# ========== 工具函数 ==========
def check_signature(token, signature, timestamp, nonce):
    """验证消息是否来自微信服务器"""
    tmp_list = sorted([token, timestamp, nonce])
    tmp_str = ''.join(tmp_list).encode('utf-8')
    tmp_str = hashlib.sha1(tmp_str).hexdigest()
    return tmp_str == signature


def call_dify_workflow(query, user_id):
    """调用Dify工作流API并返回回复文本"""
    headers = {
        'Authorization': f'Bearer {DIFY_API_KEY}',
        'Content-Type': 'application/json'
    }

    data = {
        'inputs': {"input": query},  # 根据你的工作流输入参数进行调整
        'user': user_id,
        'response_mode': 'blocking'
    }

    try:
        resp = requests.post(DIFY_WORKFLOW_URL, json=data, headers=headers, timeout=30)
        resp.raise_for_status()
        result = resp.json()

        # 解析Dify响应
        ai_reply = result.get('data', {}).get('status', None)
        if ai_reply == 'succeeded':
            ai_reply = result.get('data', {}).get('outputs', {}).get('text', None)
            if ai_reply is None:
                print(f"Dify响应结构异常: {result}")
                ai_reply = "AI助手思考中，请稍候..."
        return ai_reply[:2000]  # 微信文本消息长度限制
    except requests.exceptions.RequestException as e:
        print(f"调用Dify API网络错误: {e}")
        return "网络服务有点忙，请稍后再试。"
    except Exception as e:
        print(f"处理dify响应时出错: {e}")
        return "AI助手暂时开小差了，请稍后重试。"


def reply_text(to_user, from_user, content):
    """生成文本回复的XML格式数据"""
    create_time = int(time.time())
    reply_xml = f"""<xml>
<ToUserName><![CDATA[{to_user}]]></ToUserName>
<FromUserName><![CDATA[{from_user}]]></FromUserName>
<CreateTime>{create_time}</CreateTime>
<MsgType><![CDATA[text]]></MsgType>
<Content><![CDATA[{content}]]></Content>
</xml>"""
    return reply_xml


# ========== Flask 路由处理 ==========
@app.route('/wechat', methods=['GET'])
def wechat_verify():
    """验证微信服务器配置"""
    signature = request.args.get('signature', '')
    timestamp = request.args.get('timestamp', '')
    nonce = request.args.get('nonce', '')
    echostr = request.args.get('echostr', '')

    if check_signature(TOKEN, signature, timestamp, nonce):
        print("微信服务器验证成功！")
        return echostr
    else:
        print("微信服务器验证失败！")
        return 'Error: Invalid signature', 403


@app.route('/wechat', methods=['POST'])
def handle_wechat_message():
    """接收和处理微信用户发来的消息"""
    signature = request.args.get('signature', '')
    timestamp = request.args.get('timestamp', '')
    nonce = request.args.get('nonce', '')

    if not check_signature(TOKEN, signature, timestamp, nonce):
        return 'Error: Invalid signature', 403

    raw = request.data
    # 解析用户发来的XML消息
    root = ET.fromstring(raw)
    msg_type = root.find('MsgType').text
    from_user = root.find('FromUserName').text
    to_user = root.find('ToUserName').text

    print(f"收到消息 - 类型: {msg_type}, 来自用户: {from_user}")

    if msg_type == 'text':
        user_question = root.find('Content').text
        print(f"用户问题: {user_question}")

        # 调用Dify获取AI回复
        ai_reply = call_dify_workflow(user_question, from_user)
        print(f"AI回复: {ai_reply}")

        # 构造回复XML
        reply_xml = reply_text(from_user, to_user, ai_reply)
        response = make_response(reply_xml)
        response.content_type = 'application/xml'
        return response

    elif msg_type == 'event':
        event = root.find('Event').text
        if event == 'subscribe':
            welcome_text = "感谢关注！我是您的AI智能助手，可以回答各种问题。请直接发送消息给我吧！"
            reply_xml = reply_text(from_user, to_user, welcome_text)
            response = make_response(reply_xml)
            response.content_type = 'application/xml'
            return response
        else:
            return 'success'
    else:
        not_support_text = "暂不支持此类型消息，请发送文字内容。"
        reply_xml = reply_text(from_user, to_user, not_support_text)
        response = make_response(reply_xml)
        response.content_type = 'application/xml'
        return response


# ========== 启动服务 ==========
if __name__ == '__main__':
    print(f"微信公众号智能客服服务启动中...")
    print(f"服务地址: http://{HOST}:{PORT}/wechat")
    app.run(host=HOST, port=PORT, debug=False)