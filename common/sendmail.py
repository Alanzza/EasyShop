import os
import smtplib
from email.mime.application import MIMEApplication  # 附件
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from conf.operationConfig import OperationConfig
from common.recordlog import logs

conf = OperationConfig()


class SendEmail(object):
    """构建邮件主题、正文、附件"""

    def __init__(
            self,
            host=conf.get_section_for_data('EMAIL', 'host'),
            port=conf.get_section_for_data('EMAIL', 'port'),
            user=conf.get_section_for_data('EMAIL', 'user'),
            passwd=conf.get_section_for_data('EMAIL', 'passwd'),
            security=conf.get_section_for_data('EMAIL', 'security')
    ):
        self.__host = host
        self.__user = user
        self.__passwd = passwd
        try:
            self.__port = int(port) if port else 0
        except (TypeError, ValueError):
            self.__port = 0
        self.__security = (security or 'ssl').strip().lower()
        if self.__security not in {'ssl', 'starttls', 'none'}:
            self.__security = 'ssl'

    def build_content(self, subject, email_content, addressee=None, atta_file=None):
        """
        构建邮件格式，邮件正文、附件
        @param subject: 邮件主题
        @param addressee: 收件人，在配置文件中以;分割
        @param email_content: 邮件正文内容
        @return:
        """
        user = self.__user
        # 收件人
        if addressee is None:
            addressee = conf.get_section_for_data('EMAIL', 'addressee')
        if isinstance(addressee, (list, tuple, set)):
            recipients = [str(item).strip() for item in addressee if str(item).strip()]
        else:
            recipients = [segment.strip() for segment in str(addressee).split(';') if segment.strip()]
        if not recipients:
            logs.error('收件人列表为空，取消发送邮件')
            return
        message = MIMEMultipart()
        message['Subject'] = subject
        message['From'] = user
        message['To'] = ';'.join(recipients)

        # 邮件正文
        text = MIMEText(email_content, _subtype='plain', _charset='utf-8')
        message.attach(text)

        attachment_paths = []
        if atta_file:
            if isinstance(atta_file, (list, tuple, set)):
                attachment_paths = [str(path) for path in atta_file if str(path).strip()]
            else:
                attachment_paths = [str(atta_file)]

        for file_path in attachment_paths:
            if not os.path.isfile(file_path):
                logs.warning('附件文件不存在: %s', file_path)
                continue
            with open(file_path, 'rb') as file:
                atta = MIMEApplication(file.read())
            atta.add_header('Content-Disposition', 'attachment', filename=os.path.basename(file_path))
            message.attach(atta)

        connection = None

        try:
            if self.__security == 'ssl':
                port = self.__port or 465
                connection = smtplib.SMTP_SSL(self.__host, port)
            else:
                port = self.__port or 25
                connection = smtplib.SMTP(self.__host, port)
                if self.__security == 'starttls':
                    connection.starttls()
            connection.login(self.__user, self.__passwd)
            connection.sendmail(user, recipients, message.as_string())
        except smtplib.SMTPConnectError as e:
            logs.error('邮箱服务器连接失败：%s', e)
        except smtplib.SMTPAuthenticationError as e:
            logs.error('邮箱服务器认证错误：%s', e)
        except smtplib.SMTPSenderRefused as e:
            logs.error('发件人地址未经验证：%s', e)
        except smtplib.SMTPDataError as e:
            logs.error('发送的邮件内容包含了未被许可的信息，或被系统识别为垃圾邮件：%s', e)
        except Exception as e:
            logs.error(e)
        else:
            logs.info('邮件发送成功!')
        finally:
            if connection is not None:
                try:
                    connection.quit()
                except Exception:
                    pass


class BuildEmail(SendEmail):
    """发送邮件"""

    # def __int__(self, host, user, passwd):
    #     super(BuildEmail, self).__init__(host, user, passwd)

    def main(self, success, failed, error, not_running, atta_file=None, *args):
        """
        :param success: list类型
        :param failed: list类型
        :param error: list类型
        :param not_running: list类型
        :param atta_file: 附件路径
        :param args:
        :return:
        """
        success_num = len(success)
        fail_num = len(failed)
        error_num = len(error)
        notrun_num = len(not_running)
        total = success_num + fail_num + error_num + notrun_num
        execute_case = success_num + fail_num
        if execute_case:
            pass_result = "%.2f%%" % (success_num / execute_case * 100)
            fail_result = "%.2f%%" % (fail_num / execute_case * 100)
            err_result = "%.2f%%" % (error_num / execute_case * 100)
        else:
            pass_result = fail_result = err_result = "0.00%"
        # 设置邮件主题、收件人、内容
        subject = conf.get_section_for_data('EMAIL', 'subject')
        addressee = conf.get_section_for_data('EMAIL', 'addressee')
        content = (
            "***项目接口测试，共测试接口%s个，通过%s个，失败%s个，错误%s个，未执行%s个，"
            "通过率%s，失败率%s，错误率%s。详细测试结果请参见附件。"
            % (total, success_num, fail_num, error_num, notrun_num, pass_result, fail_result, err_result)
        )
        self.build_content(subject, content, addressee, atta_file)
