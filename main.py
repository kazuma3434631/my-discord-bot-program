import discord
from discord.ext import commands
from discord import app_commands
import os
import re
import datetime
from collections import defaultdict
from keep_alive import keep_alive

# --- 1. 権限（Intents）の設定 ---
intents = discord.Intents.default()
intents.members = True 
intents.message_content = True 
intents.voice_states = True 

# --- 2. 設定（IDを統合・整理） ---
# 指定された行動記録用チャンネル
ACTION_LOG_ID = 1475867868724854814

# 既存のID
LOG_CHANNEL_ID = 1475491103225417738 # メッセージ削除/編集用
WELCOME_CHANNEL_ID = 1475484575114330162
TICKET_CATEGORY_ID = 1475853559399452752
VC_CREATOR_ID = 1475482867818827829

# 管理用メモリ
last_messages = defaultdict(list)
temp_channels = [] 

# --- 3. ロギング用関数 ---
async def send_action_log(bot, title, description, color=discord.Color.blue(), fields=None):
    """Botの行動を共通チャンネルに記録する関数"""
    ch = bot.get_channel(ACTION_LOG_ID)
    if not ch: return
    
    emb = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.datetime.now()
    )
    if fields:
        for name, value in fields.items():
            emb.add_field(name=name, value=value, inline=False)
    emb.set_footer(text="Bot Action Logger")
    
    try:
        await ch.send(embed=emb)
    except:
        print(f"行動ログの送信に失敗しました (ID: {ACTION_LOG_ID})")

# --- 4. UIクラス（役職・チケット・お掃除） ---

class RoleButton(discord.ui.Button):
    def __init__(self, role: discord.Role):
        super().__init__(label=role.name, style=discord.ButtonStyle.primary, custom_id=f"role_{role.id}")
    async def callback(self, it: discord.Interaction):
        role = it.guild.get_role(int(self.custom_id.split("_")[1]))
        if not role: return await it.response.send_message("役職が見つからなかったよ…", ephemeral=True)
        if role in it.user.roles:
            await it.user.remove_roles(role)
            await it.response.send_message(f"役職「{role.name}」を外したよ！", ephemeral=True)
        else:
            await it.user.add_roles(role)
            await it.response.send_message(f"役職「{role.name}」を付けたよ！", ephemeral=True)

class RolePanelView(discord.ui.View):
    def __init__(self, roles=None):
        super().__init__(timeout=None)
        if roles:
            for role in roles: self.add_item(RoleButton(role))

class ConfirmCloseView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="本当に閉じる", style=discord.ButtonStyle.danger, custom_id="confirm_close")
    async def confirm_close(self, it: discord.Interaction, button: discord.ui.Button):
        await send_action_log(it.client, "🎫 チケット削除", f"実行者: {it.user.mention}\nチャンネル: {it.channel.name}", discord.Color.red())
        await it.channel.delete()

class CloseTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="チケットを閉じる", style=discord.ButtonStyle.secondary, emoji="🔒", custom_id="close_ticket")
    async def close_ticket(self, it: discord.Interaction, button: discord.ui.Button):
        await it.response.send_message("このチケットを閉じても大丈夫かな？", view=ConfirmCloseView(), ephemeral=True)

class TicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    
    async def create_ticket_logic(self, it: discord.Interaction, ticket_type: str, color: discord.Color):
        await it.response.defer(ephemeral=True)
        guild, user = it.guild, it.user
        category = guild.get_channel(TICKET_CATEGORY_ID)
        
        if not category:
            return await it.followup.send("カテゴリーが見つかりませんでした。", ephemeral=True)

        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
            }
            channel = await guild.create_text_channel(name=f"🎫｜{ticket_type}-{user.display_name}", overwrites=overwrites, category=category)
            await it.followup.send(f"チケットを作成しました：{channel.mention}", ephemeral=True)
            await channel.send(embed=discord.Embed(title=f"【{ticket_type}】窓口", description=f"{user.mention}さん、内容を入力してください。", color=color), view=CloseTicketView())
            
            # 行動ログに記録
            await send_action_log(it.client, "🎫 チケット作成", f"タイプ: {ticket_type}\n作成者: {user.mention}\nチャンネル: {channel.mention}", color)
            
        except Exception as e:
            await it.followup.send(f"失敗しました：`{e}`", ephemeral=True)

    @discord.ui.button(label="🚨 通報", style=discord.ButtonStyle.danger, custom_id="ticket_report")
    async def report(self, it: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_logic(it, "通報", discord.Color.red())

    @discord.ui.button(label="❓ 質問", style=discord.ButtonStyle.primary, custom_id="ticket_question")
    async def question(self, it: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_logic(it, "質問", discord.Color.blue())

    @discord.ui.button(label="💡 提案", style=discord.ButtonStyle.success, custom_id="ticket_suggest")
    async def suggest(self, it: discord.Interaction, button: discord.ui.Button):
        await self.create_ticket_logic(it, "提案", discord.Color.green())

# --- 5. Bot本体 ---
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='/', intents=intents)

    async def setup_hook(self):
        self.add_view(TicketView())
        self.add_view(CloseTicketView())
        self.add_view(ConfirmCloseView())
        self.add_view(RolePanelView())
        await self.tree.sync()

bot = MyBot()

# --- 6. イベント処理 ---

@bot.event
async def on_ready():
    print(f'ログイン完了: {bot.user.name}')
    await send_action_log(bot, "🚀 Bot起動", "システムが正常にオンラインになりました。", discord.Color.green())

# VC自動作成
@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and after.channel.id == VC_CREATOR_ID:
        try:
            new_ch = await member.guild.create_voice_channel(name=f"🔊｜{member.display_name}の部屋", category=after.channel.category)
            await member.move_to(new_ch)
            temp_channels.append(new_ch.id)
            await send_action_log(bot, "🔊 VC作成", f"作成者: {member.mention}\nチャンネル: {new_ch.name}")
        except: pass
    if before.channel and before.channel.id in temp_channels and len(before.channel.members) == 0:
        try:
            ch_name = before.channel.name
            await before.channel.delete()
            temp_channels.remove(before.channel.id)
            await send_action_log(bot, "🗑 VC削除", f"空になったため削除しました: {ch_name}", discord.Color.light_grey())
        except: pass

# メッセージ防衛・リンク展開
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    # スパム制限
    if len(message.mentions) >= 5 or (len(last_messages[message.author.id]) >= 3 and len(set(m["content"] for m in last_messages[message.author.id][-3:])) == 1):
        await message.delete()
        await send_action_log(bot, "🛡 スパム防御", f"実行者: {message.author.mention}\n理由: 大量メンションまたは連投", discord.Color.gold())
        return
    # 履歴保存
    last_messages[message.author.id].append({"content": message.content, "time": datetime.datetime.now()})
    
    # リンク展開
    extract = re.search(r"https://(?:ptb\.|canary\.)?discord\.com/channels/(\d+)/(\d+)/(\d+)", message.content)
    if extract:
        g, c, m = map(int, extract.groups())
        if message.guild.id == g:
            try:
                f_msg = await bot.get_channel(c).fetch_message(m)
                emb = discord.Embed(description=f_msg.content, color=discord.Color.light_grey(), timestamp=f_msg.created_at)
                emb.set_author(name=f_msg.author.display_name, icon_url=f_msg.author.display_avatar.url)
                if f_msg.attachments: emb.set_image(url=f_msg.attachments[0].url)
                await message.reply(embed=emb, mention_author=False)
                await send_action_log(bot, "🔗 リンク展開", f"展開者: {message.author.mention}\n元メッセージID: {m}")
            except: pass
    await bot.process_commands(message)

# メッセージ削除・編集ログ (LOG_CHANNEL_ID用)
@bot.event
async def on_message_delete(message):
    if message.author.bot: return
    log = bot.get_channel(LOG_CHANNEL_ID)
    if log:
        emb = discord.Embed(title="🗑 メッセージ削除", color=discord.Color.red(), timestamp=message.created_at)
        emb.add_field(name="書いた人", value=message.author.mention)
        emb.add_field(name="内容", value=message.content or "画像など", inline=False)
        try: await log.send(embed=emb)
        except: pass

# --- 7. スラッシュコマンド（行動記録対応） ---

@bot.tree.command(name="say", description="【管理者】Botが代わりに喋ります")
@app_commands.checks.has_permissions(administrator=True)
async def say(it: discord.Interaction, message: str):
    sent_msg = await it.channel.send(message)
    await it.response.send_message(f"送信完了。修正用ID: `{sent_msg.id}`", ephemeral=True)
    await send_action_log(bot, "💬 Sayコマンド利用", f"実行者: {it.user.mention}\n内容: {message}\nID: `{sent_msg.id}`")

@bot.tree.command(name="edit", description="【管理者】Botのメッセージを書き換えます")
@app_commands.checks.has_permissions(administrator=True)
async def edit(it: discord.Interaction, message_id: str, new_message: str):
    await it.response.defer(ephemeral=True)
    try:
        msg = await it.channel.fetch_message(int(message_id))
        if msg.author != bot.user:
            return await it.followup.send("Bot自身のメッセージではありません。", ephemeral=True)
        old_content = msg.content
        await msg.edit(content=new_message)
        await it.followup.send("書き換え完了！", ephemeral=True)
        await send_action_log(bot, "📝 Editコマンド利用", f"実行者: {it.user.mention}\n旧内容: {old_content}\n新内容: {new_message}", discord.Color.orange())
    except:
        await it.followup.send("メッセージが見つかりませんでした。", ephemeral=True)

@bot.tree.command(name="clear", description="【管理者】お掃除します")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(it: discord.Interaction, amount: int):
    await it.response.defer(ephemeral=True)
    deleted = await it.channel.purge(limit=amount)
    await it.followup.send(f"{len(deleted)}件削除しました。", ephemeral=True)
    await send_action_log(bot, "🧹 Clear実行", f"実行者: {it.user.mention}\n削除数: {len(deleted)}\nチャンネル: {it.channel.name}", discord.Color.purple())

@bot.tree.command(name="ticket_setup", description="【管理者】窓口を設置")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_setup(it: discord.Interaction):
    await it.channel.send(embed=discord.Embed(title="📩 お問い合わせ窓口", color=discord.Color.blue()), view=TicketView())
    await it.response.send_message("設置完了", ephemeral=True)
    await send_action_log(bot, "⚙️ システム設定", f"実行者: {it.user.mention}\n内容: チケット窓口設置", discord.Color.blue())

@bot.tree.command(name="ping", description="疎通確認")
async def ping(it: discord.Interaction):
    await it.response.send_message(f"Pong! {round(bot.latency * 1000)}ms", ephemeral=True)

# 実行
keep_alive()
bot.run(os.getenv('DISCORD_TOKEN'))
