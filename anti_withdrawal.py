'''
Author: sineom h.sineom@gmail.com
Date: 2024-11-11 14:17:56
LastEditors: sineom h.sineom@gmail.com
LastEditTime: 2024-11-11 17:25:17
FilePath: /chatgpt-on-wechat/plugins/anti_withdrawal/anti_withdrawal.py
Description: 防止撤回消息

Copyright (c) 2024 by sineom, All Rights Reserved. 
'''
import plugins
import json
import os
import re
from threading import Timer
import time
from channel.wechat.wechat_channel import WechatChannel
from channel.wechat.wechat_message import WechatMessage
from plugins import *
from common.log import logger
from lib.itchat.content import *
from lib import itchat

@plugins.register(
    name="anti_withdrawal",
    desire_priority=99,
    namecn="防止撤回",
    desc="防止微信消息撤回插件",
    version="1.0",
    author="sineom",
)
class AntiWithdrawal(Plugin):
    def __init__(self):
        super().__init__()
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        logger.info("[AntiWithdrawal] inited")
        self.config = {}
        # 初始化存储
        self.msg_dict = {}
        self.out_date_msg_dict = []
        self.receivedMsgs = {}
        self.target_friend = None
        self.download_directory = './plugins/anti_withdrawal/downloads'
        
        # 加载配置
        self.load_config()
        
        # 确保下载目录存在
        if not os.path.exists(self.download_directory):
            os.makedirs(self.download_directory)
            
        # 启动定时清理
        self.start_cleanup_timer()

    def load_config(self):
        """加载配置文件"""
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            else:
                # 默认配置
                self.config = {
                    "receiver": {
                        "type": "remark_name",
                        "name": "文件传输助手"
                    },
                    "message_expire_time": 120,
                    "cleanup_interval": 2
                }
                # 保存默认配置
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.config, f, indent=4, ensure_ascii=False)
            
            logger.info(f"[AntiWithdrawal] 加载配置成功: {self.config}")
        except Exception as e:
            logger.error(f"[AntiWithdrawal] 加载配置失败: {str(e)}")
            # 使用默认值
            self.config = {
               "receiver": {
                        "type": "remark_name",
                        "name": "文件传输助手"
                    },
                "message_expire_time": 120,
                "cleanup_interval": 2
            }

    def get_help_text(self, **kwargs):
        help_text = "防撤回插件使用说明:\n"
        help_text += "本插件会自动保存最近消息并在检测到撤回时转发给指定接收者\n\n"
        return help_text

    def get_revoke_msg_receiver(self):
        """获取接收撤回消息的好友"""
        if self.target_friend is None:
            friends = itchat.get_friends(update=True)
            receiver_config = self.config.get("receiver", {})
            match_type = receiver_config.get("type", "remark_name")
            match_name = receiver_config.get("name", "")
            
            for friend in friends:
                if match_type == "nickname" and friend['NickName'] == match_name:
                    self.target_friend = friend
                    break
                elif match_type == "remark_name" and friend['RemarkName'] == match_name:
                    self.target_friend = friend
                    break
                    
            if self.target_friend is None:
                logger.error(f"[AntiWithdrawal] 未找到接收者: {match_type}={match_name}")
                
        return self.target_friend

    def start_cleanup_timer(self):
        """启动定时清理"""
        def delete_out_date_msg():
            current_time = int(time.time())
            expire_time = self.config.get("message_expire_time", 120)
            # 找出过期消息
            for msg_id in self.msg_dict:
                if (current_time - self.msg_dict[msg_id]['CreateTime']) > expire_time:
                    self.out_date_msg_dict.append(msg_id)
            
            # 删除过期消息
            for msg_id in self.out_date_msg_dict:
                msg = self.msg_dict[msg_id]
                if msg['Type'] == 'Text':
                    self.msg_dict.pop(msg_id)
                elif msg['Type'] in ['Picture', 'Video', 'Attachment']:
                    file_path = msg['FileName']
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    self.msg_dict.pop(msg_id)
                    
            self.out_date_msg_dict.clear()
            cleanup_interval = self.config.get("cleanup_interval", 2)
            t = Timer(cleanup_interval, delete_out_date_msg)
            t.start()
            
        delete_out_date_msg()

    def download_files(self, msg):
        """下载文件"""
        file_path = os.path.join(self.download_directory, msg['FileName'])
        msg['Text'](file_path)
        return '@%s@%s' % (
            {'Picture': 'img', 'Video': 'vid', 'Attachment': 'fil'}.get(msg['Type'], 'fil'),
            file_path
        )

    def handle_revoke(self, msg, is_group=False):
        """处理撤回消息"""
        match = re.search('撤回了一条消息', msg['Content'])
        if not match:
            return
            
        old_msg_id = re.search(r"\<msgid\>(.*?)\<\/msgid\>", msg['Content']).group(1)
        if old_msg_id not in self.msg_dict:
            return
            
        old_msg = self.msg_dict[old_msg_id]
        target_friend = self.get_revoke_msg_receiver()
        if target_friend is None:
            return

        try:
            if old_msg['Type'] == 'Text':
                prefix = f"群：【{msg['User']['NickName']}】的【{msg['ActualNickName']}】" if is_group else f"【{msg['User']['NickName']}】"
                text = f"{prefix}刚刚发过这条消息：{old_msg['Text']}"
                itchat.send(msg=text, toUserName=target_friend['UserName'])
                
            elif old_msg['Type'] in ['Picture', 'Video', 'Attachment']:
                msg_type = {'Picture': '图片', 'Video': '视频', 'Attachment': '文件'}[old_msg['Type']]
                prefix = f"群：【{msg['User']['NickName']}】的【{msg['ActualNickName']}】" if is_group else f"【{msg['User']['NickName']}】"
                text = f"{prefix}刚刚发过这条{msg_type}👇"
                itchat.send_msg(msg=text, toUserName=target_friend['UserName'])
                
                file_info = old_msg['FileName']
                if old_msg['Type'] == 'Picture':
                    itchat.send_image(file_info, toUserName=target_friend['UserName'])
                elif old_msg['Type'] == 'Video':
                    itchat.send_video(file_info, toUserName=target_friend['UserName'])
                else:
                    itchat.send_file(file_info, toUserName=target_friend['UserName'])
        except Exception as e:
            logger.error(f"发送撤回消息失败: {str(e)}")

    def handle_msg(self, msg, is_group=False):
        """处理消息"""
        try:
            msg_id = msg['MsgId']
            if msg_id in self.receivedMsgs:
                return
                
            self.receivedMsgs[msg_id] = True
            create_time = msg['CreateTime']
            
            if int(create_time) < int(time.time()) - 60:
                return
                
            if msg["Type"] == 'Text':
                self.msg_dict[msg_id] = msg
            elif msg["Type"] in ['Picture', 'Video', 'Attachment']:
                self.msg_dict[msg_id] = msg
                file_info = self.download_files(msg)
                self.msg_dict[msg_id]['FileName'] = file_info.split('@')[-1]
            elif msg["Type"] == 'Note':
                self.handle_revoke(msg, is_group)
                
        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}")
    
    def on_handle_context(self, e_context: EventContext):
        context = e_context['context']
        if context.get("isgroup", False):
            self.handle_group_msg(context)
        else:
            self.handle_single_msg(context)
        e_context.action = EventAction.CONTINUE

    def handle_single_msg(self, msg):
        """处理私聊消息"""
        self.handle_msg(msg, False)
        return None

    def handle_group_msg(self, msg):
        """处理群聊消息"""
        self.handle_msg(msg, True)
        return None
