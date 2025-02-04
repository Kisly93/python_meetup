from datetime import datetime
from datetime import timedelta
import logging

from django.utils import timezone
import telegram
from django.core.management.base import BaseCommand
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
    LabeledPrice,
)
from telegram.ext import (
    Updater,
    Filters,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    PreCheckoutQueryHandler,
)

from bot.models import (
    Member,
    Report,
    Question,
)

from python_meetup import settings
from bot.bot_description import (
    DESCRIPTION,
    TEXT,
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s',
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Команда для запуска телеграм-бота
    """

    def handle(self, *args, **kwargs):
        updater = Updater(token=settings.tg_token, use_context=True)
        dispatcher = updater.dispatcher

        def start_conversation(update, context):
            chat_id = update.effective_chat.id
            username = update.effective_chat.username
            query = update.callback_query
            try:
                member = Member.objects.get(chat_id=str(chat_id))
            except Member.DoesNotExist:
                member = Member.objects.create(chat_id=str(chat_id),
                                               name=username)
            if member.is_organizer:
                keyboard = [
                    [
                        InlineKeyboardButton('План мероприятия',
                                             callback_data='to_currrent'),

                        InlineKeyboardButton('Перенос докладов',
                                             callback_data='input_time'),
                    ],
                ]
            elif member.is_speaker:
                keyboard = [
                    [
                        InlineKeyboardButton('Посмотреть вопросы',
                                             callback_data='get_questions'),
                        InlineKeyboardButton('Донат',
                                             callback_data='to_donate'),
                    ],
                    [
                        InlineKeyboardButton('План мероприятия',
                                             callback_data='to_currrent'),
                    ],
                    [
                        InlineKeyboardButton('О боте',
                                             callback_data='about_bot'),
                    ],
                ]
            else:
                keyboard = [
                    [
                        InlineKeyboardButton('План мероприятия',
                                             callback_data='to_currrent'),
                        InlineKeyboardButton('Донат',
                                             callback_data='to_donate'),
                    ],
                    [
                        InlineKeyboardButton('О боте',
                                             callback_data='about_bot'),
                    ],
                ]
            txt = 'Здравствуйте, {}! \nРады приветствовать Вас на нашей конференции!'
            if query and query.data == 'to_start' and context.user_data.get('invoice_sended', False):
                query.edit_message_text(
                    text=txt.format(username),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )
                context.user_data['invoice_sended'] = False
            else:
                if query:
                    context.bot.delete_message(chat_id=chat_id, message_id=query.message.message_id)

                context.bot.send_message(
                    chat_id=chat_id,
                    text=txt.format(username),
                    reply_markup=InlineKeyboardMarkup(keyboard),
                )

            return 'MAIN_MENU'

        def input_time(update, context):
            query = update.callback_query

            now = datetime.now()
            current_report = Report.objects.filter(start_at__lte=now,
                                                   end_at__gte=now).first()
            if not current_report:
                query.answer(text="На текущий момент нет доклада.")
                return 'REPORTS'
            keyboard = [
                [InlineKeyboardButton('На главную',
                                      callback_data='to_start')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            query.answer()
            query.edit_message_text(
                text=TEXT['minutes'],
                reply_markup=reply_markup,
                parse_mode=telegram.ParseMode.MARKDOWN,
            )

            return 'SHIFT_REPORTS'

        def get_questions(update, context):
            query = update.callback_query
            chat_id = update.effective_chat.id

            questions = Question.objects.filter(responder__chat_id=chat_id)

            keyboard = [
                [
                    InlineKeyboardButton('На главную',
                                         callback_data='to_start'),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.answer()

            if questions.exists():
                questions_text = '\n\n'.join(f'{i+1}. (Слушатель: @{quest.asker.name})\n   Вопрос: {quest.title}' for i, quest in enumerate(questions))
                message_text = f'Адресованные вам вопросы:\n\n{questions_text}'
            else:
                message_text = 'У вас пока нет адресованных вопросов.'

            query.edit_message_text(
                text=message_text,
                reply_markup=reply_markup,
                parse_mode=telegram.ParseMode.HTML,
            )
            return 'GET_QUESTIONS'

        def show_abilities(update, _):
            query = update.callback_query

            keyboard = [
                [
                    InlineKeyboardButton('Вернуться на главную',
                                         callback_data='to_start'),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.answer()
            query.edit_message_text(
                text=DESCRIPTION,
                reply_markup=reply_markup,
                parse_mode=telegram.ParseMode.MARKDOWN,
            )
            return 'ABILITIES'

        def show_conference_program(update, context):
            query = update.callback_query
            keyboard = [
                [
                    InlineKeyboardButton('Предыдущий',
                                         callback_data='to_previous'),
                    InlineKeyboardButton('Текущий',
                                         callback_data='to_currrent'),
                    InlineKeyboardButton('Следующий',
                                         callback_data='to_next'),
                ],
                [
                    InlineKeyboardButton('Программа конференции',
                                         callback_data='to_program'),
                    InlineKeyboardButton('Задать вопрос',
                                         callback_data='ask_question'),
                ],
                [
                    InlineKeyboardButton('На главную',
                                         callback_data='to_start'),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            query.answer()
            context.chat_data['chat_id'] = ''
            if query.data == 'to_previous':
                trend = context.chat_data['trend']
                if trend == 'left':
                    report_id = context.chat_data['report_id']
                else:
                    context.chat_data['trend'] = 'left'
                    report_id = 0
                now = datetime.now()
                reports = Report.objects.select_related('speaker') \
                    .filter(end_at__lt=now)
                if reports and (reports.count() > report_id):
                    report = reports.order_by('-end_at')[report_id]
                    context.chat_data['report_id'] = report_id + 1
                    context.chat_data['chat_id'] = report.speaker.chat_id
                    txt = TEXT['report'] \
                        .format(report.title, report.speaker,
                                timezone.localtime(report.start_at),
                                timezone.localtime(report.end_at))
                else:
                    txt = 'Докладов еще не было'
                query.edit_message_text(
                    text=txt,
                    reply_markup=reply_markup,
                    parse_mode=telegram.ParseMode.HTML,
                )
            elif query.data == 'to_currrent':
                context.chat_data['report_id'] = 0
                context.chat_data['trend'] = ''
                now = datetime.now()
                report = Report.objects.select_related('speaker') \
                    .filter(start_at__lt=now, end_at__gt=now).first()
                if report:
                    context.chat_data['chat_id'] = report.speaker.chat_id
                    txt = TEXT['report'] \
                        .format(report.title, report.speaker,
                                timezone.localtime(report.start_at),
                                timezone.localtime(report.end_at))
                else:
                    txt = 'Докладов сейчас нет'
                query.edit_message_text(
                    text=txt,
                    reply_markup=reply_markup,
                    parse_mode=telegram.ParseMode.HTML,
                )
            elif query.data == 'to_next':
                trend = context.chat_data['trend']
                if trend == 'right':
                    report_id = context.chat_data['report_id']
                else:
                    context.chat_data['trend'] = 'right'
                    report_id = 0
                now = datetime.now()
                reports = Report.objects.select_related('speaker') \
                    .filter(start_at__gt=now)
                print(reports.count(), report_id)
                if reports and (reports.count() > report_id):
                    report = reports.order_by('start_at')[report_id]
                    context.chat_data['report_id'] = report_id + 1
                    context.chat_data['chat_id'] = report.speaker.chat_id
                    txt = TEXT['report'] \
                        .format(report.title, report.speaker,
                                timezone.localtime(report.start_at),
                                timezone.localtime(report.end_at))
                else:
                    txt = 'Докладов больше нет'
                query.edit_message_text(
                    text=txt,
                    reply_markup=reply_markup,
                    parse_mode=telegram.ParseMode.HTML,
                )
            elif query.data == 'to_program':
                now = datetime.now()
                reports = Report.objects.all().order_by('start_at')
                txt = ''
                if reports:
                    for report in reports:
                        title = report.title
                        speaker = report.speaker
                        start_at = timezone.localtime(report.start_at).time()
                        end_at = timezone.localtime(report.end_at).time()
                        txt = f'{txt} \n{title} \n{speaker} \n{start_at} - {end_at}'
                else:
                    txt = 'Докладов нет'
                query.edit_message_text(
                    text=txt,
                    reply_markup=reply_markup,
                    parse_mode=telegram.ParseMode.HTML,
                )

            return 'REPORTS'

        def ask_question(update, context):
            query = update.callback_query
            asker_name = Member.objects.get(chat_id=query.message.chat.id).name
            chat_id = context.chat_data['chat_id']
            if not chat_id:
                query.answer(text="Выберите доклад и спикера.")
                return 'REPORTS'

            responder = Member.objects.get(chat_id=chat_id)
            context.chat_data['asker'] = asker_name
            context.chat_data['responder_id'] = responder.id

            keyboard = [
                [InlineKeyboardButton('На главную', callback_data='to_start')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            query.answer()
            query.edit_message_text(
                text=f'Введите вопрос для докладчика {responder.name}:',
                reply_markup=reply_markup,
                parse_mode=telegram.ParseMode.HTML,
            )

            return 'SAVE_QUESTION'

        def save_question(update, context):
            question_text = update.message.text
            asker_name = context.chat_data.get('asker')
            responder_id = context.chat_data.get('responder_id')

            asker = Member.objects.get(name=asker_name)
            responder = Member.objects.get(id=responder_id)

            question = Question(
                title=question_text,
                asker=asker,
                responder=responder)
            question.save()

            context.bot.send_message(chat_id=update.message.chat_id,
                                     text='Ваш вопрос сохранен')

            keyboard = [
                [InlineKeyboardButton('На главную',
                                      callback_data='to_start')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            update.message.reply_text(text='Спасибо за ваш вопрос!',
                                      reply_markup=reply_markup,
                                      parse_mode=telegram.ParseMode.MARKDOWN,)

            return 'SAVE_QUESTION'

        def shift_reports(update, context):

            try:
                minutes = int(update.message.text)
            except ValueError:
                return 'INPUT_TIME'

            now = datetime.now()
            current_report = Report.objects.filter(start_at__lt=now,
                                                   end_at__gt=now).first()
            future_reports = Report.objects.filter(start_at__gt=now)

            if current_report:
                current_report.end_at += timedelta(minutes=minutes)
                current_report.save()

            for report in future_reports:
                report.start_at += timedelta(minutes=minutes)
                report.end_at += timedelta(minutes=minutes)
                report.save()
                txt = f'Ваш доклад сдвинут на {minutes} минут!'
                try:
                    context.bot.send_message(chat_id=report.speaker.chat_id,
                                             text=txt)
                except telegram.error.BadRequest:
                    pass

            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton('На главную',
                                       callback_data='to_start')]])

            context.bot.send_message(chat_id=update.effective_chat.id,
                                     text=f'Время всех докладов успешно сдвинуто на {minutes} минут.',
                                     reply_markup=reply_markup)
            return 'SHIFT_REPORTS'

        def ask_amount(update, context):
            query = update.callback_query
            query.answer()
            query.message.reply_text('Сколько вы хотите донатить?')
            return 'SEND_INVOICE'

        def send_invoice(update, context):
            amount_in_rubles = int(update.message.text)
            amount_in_kopecks = amount_in_rubles * 100

            token = settings.payments_token
            chat_id = update.effective_message.chat_id
            context.user_data['invoice_sended'] = True

            keyboard = [
                [InlineKeyboardButton('Оплатить', pay=True)],
                [InlineKeyboardButton('На главную',
                                      callback_data='to_start'), ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            context.bot.send_invoice(
                chat_id=chat_id,
                title='Донат',
                description='Донат',
                payload='payload',
                provider_token=token,
                currency='RUB',
                need_phone_number=False,
                need_email=False,
                is_flexible=False,
                prices=[
                    LabeledPrice(label='Донат', amount=amount_in_kopecks)
                ],
                start_parameter='test',
            )
            return 'SUCCESS_PAYMENT'

        def process_pre_checkout_query(update, context):
            query = update.pre_checkout_query
            try:
                pass
            except:
                context.bot.answer_pre_checkout_query(
                    pre_checkout_query_id=query.id,
                    ok=False,
                    error_message="Что-то пошло не так...",
                )
            else:
                context.bot.answer_pre_checkout_query(query.id, ok=True)

        def success_payment(update, context):
            '''Обработка успешной оплаты'''
            amount = update.message.successful_payment.total_amount / 100
            text = f'✅ Спасибо за оплату {amount} руб.!\n\n'
            keyboard = [
                [
                    InlineKeyboardButton("На главный",
                                         callback_data="to_start"),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            update.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=telegram.ParseMode.HTML,
            )

            return 'SUCCESS_PAYMENT'

        def cancel(update, _):
            update.message.reply_text('До новых встреч',
                                      reply_markup=ReplyKeyboardRemove(),)
            return ConversationHandler.END
            
        pre_checkout_handler = PreCheckoutQueryHandler(process_pre_checkout_query)
        success_payment_handler = MessageHandler(Filters.successful_payment,
                                                 success_payment)
        dispatcher.add_handler(pre_checkout_handler)
        dispatcher.add_handler(success_payment_handler)
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start_conversation),
                          CallbackQueryHandler(start_conversation,
                                               pattern='to_start'),
                          ],
            states={
                'MAIN_MENU': [
                    CallbackQueryHandler(show_conference_program,
                                         pattern='to_currrent'),
                    CallbackQueryHandler(get_questions,
                                         pattern='get_questions'),
                    CallbackQueryHandler(show_abilities,
                                         pattern='about_bot'),
                    CallbackQueryHandler(ask_amount,
                                         pattern='to_donate'),

                    CallbackQueryHandler(input_time,
                                         pattern='input_time'),
                ],
                'REPORTS': [
                    CallbackQueryHandler(show_conference_program,
                                         pattern='to_previous'),
                    CallbackQueryHandler(show_conference_program,
                                         pattern='to_currrent'),
                    CallbackQueryHandler(show_conference_program,
                                         pattern='to_next'),
                    CallbackQueryHandler(show_conference_program,
                                         pattern='to_program'),
                    CallbackQueryHandler(ask_question,
                                         pattern='ask_question'),
                    CallbackQueryHandler(start_conversation,
                                         pattern='to_start'),
                ],
                'GET_QUESTIONS': [
                    CallbackQueryHandler(start_conversation,
                                         pattern='to_start'),
                ],
                'START_MEETING': [
                    CallbackQueryHandler(start_conversation,
                                         pattern='to_start'),
                ],
                'END_MEETING': [
                    CallbackQueryHandler(start_conversation,
                                         pattern='to_start'),
                ],
                'ASK_QUESTION': [
                    CallbackQueryHandler(start_conversation,
                                         pattern='to_start'),
                ],
                'INPUT_TIME': [
                    CallbackQueryHandler(start_conversation,
                                         pattern='to_start'),
                ],
                'ABILITIES': [
                    CallbackQueryHandler(start_conversation,
                                         pattern='to_start'),
                ],
                'SHIFT_REPORTS': [
                    CallbackQueryHandler(start_conversation,
                                         pattern='to_start'),
                    MessageHandler(Filters.text & ~Filters.command,
                                   shift_reports),
                ],
                'SAVE_QUESTION': [
                    CallbackQueryHandler(start_conversation,
                                         pattern='to_start'),
                    MessageHandler(Filters.text & ~Filters.command,
                                   save_question),
                ],
                'ASK_AMOUNT': [
                    MessageHandler(Filters.text & ~Filters.command,
                                   ask_amount)
                ],
                'SEND_INVOICE': [
                    CallbackQueryHandler(ask_amount, pattern='donate'),
                    MessageHandler(Filters.text & ~Filters.command,
                                   send_invoice),
                ],
                'PROCESS_PRE_CHECKOUT': [
                    PreCheckoutQueryHandler(process_pre_checkout_query),
                    CallbackQueryHandler(success_payment,
                                         pattern='success_payment'),
                ],
                'SUCCESS_PAYMENT': [
                    CallbackQueryHandler(start_conversation,
                                         pattern='to_start'),
                ],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
        )

        dispatcher.add_handler(conv_handler)
        start_handler = CommandHandler('start', start_conversation)
        dispatcher.add_handler(start_handler)
        dispatcher.add_handler(CallbackQueryHandler(send_invoice,
                                                    pattern='to_pay_now'))
        
        updater.start_polling()
        updater.idle()
