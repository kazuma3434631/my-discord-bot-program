import discord
from discord.ext import commands
from discord import app_commands
import os
import re
import datetime
from collections import defaultdict
from keep_alive import keep_alive

# --- 1. 権限（Intents）の設定 ---
# 注意: Discord Developer Portalで「SERVER MEMBERS INTENT」を必ずONにしてください
intents = discord.Intents.default()
intents.members = True 
intents.message_content = True 
intents.voice_states = True 

# --- 2. 設定（IDを統合・整理） ---
ACTION_LOG_ID = 1475867868724854814  # Bot自身の行動記録
LOG_CHANNEL_ID = 1475491103225417738   # ユーザーの削除/編集ログ
WELCOME_CHANNEL_ID = 1475484575114330162 # 入退室挨拶
TICKET_CATEGORY_ID = 1475853559399452752 # チケット作成先
VC_CREATOR_ID = 1475482867818827829      # VC作成チャンネル

# 管理用メモリ
last_messages = defaultdict(list)
temp_channels = [] 

# --- 3. ロギング用共通関数 ---
async def send_action_log(bot, title, description, color=discord.Color.blue(), fields=None):
    ch = bot.get_channel(ACTION_LOG_ID)
    if not ch: return
    emb = discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.now())
    if fields:
        for name, value in fields.items():
            emb.add_field(name=name, value=value, inline=False)
    emb.set_footer(text="Bot Action Logger")
    try: await ch.send(embed=emb)
    except: pass

# --- 4. UIクラス ---

class RoleButton(discord.ui.Button):
    def __init__(self, role: discord.Role):
        super().__init__(label=role.name, style=discord.ButtonStyle.primary, custom_id=f"role_{role.id}")
    async def callback(self, it: discord.Interaction):
        role = it.guild.get_role(int(self.custom_id.split("_")[1]))
        if not role: return await it.response.send_message("役職が見つからないよ", ephemeral=True)
        if role in it.user.roles:
            await it.user.remove_roles(role)
            await it.response.send_message(f"役職「{role.name}」を外したよ", ephemeral=True)
        else:
            await it.user.add_roles(role)
            await it.response.send_message(f"役職「{role.name}」を付けたよ", ephemeral=True)

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
        if not category: return await it.followup.send("カテゴリーが見つかりません", ephemeral=True)
        try:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
            }
            ch = await guild.create_text_channel(name=f"🎫｜{ticket_type}-{user.display_name}", overwrites=overwrites, category=category)
            await it.followup.send(f"チケットを作成したよ：{ch.mention}", ephemeral=True)
            await ch.send(embed=discord.Embed(title=f"【{ticket_type}】窓口", description=f"{user.mention}さん、内容を入力してね", color=color), view=CloseTicketView())
            await send_action_log(it.client, "🎫 チケット作成", f"タイプ: {ticket_type}\n作成者: {user.mention}", color)
        except Exception as e: await it.followup.send(f"失敗：`{e}`", ephemeral=True)

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
        self.add_view(TicketView()); self.add_view(CloseTicketView()); self.add_view(ConfirmCloseView()); self.add_view(RolePanelView())
        await self.tree.sync()

bot = MyBot()

# --- 6. イベント処理 ---

@bot.event
async def on_ready():
    print(f'ログイン: {bot.user.name}')
    await send_action_log(bot, "🚀 Bot起動", "システムがオンラインになりました", discord.Color.green())

@bot.event
async def on_member_join(member):
    print(f"DEBUG: 入室検知 -> {member.display_name}")
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if ch:
        try: await ch.send(f"✨ {member.display_name}さん、こんにちは！ゆっくりしていってね！")
        except: pass

@bot.event
async def on_member_remove(member):
    print(f"DEBUG: 退出検知 -> {member.display_name}")
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if ch:
        try: await ch.send(f"👋 {member.display_name}さんが行ったよ。またね！")
        except: pass

@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and after.channel.id == VC_CREATOR_ID:
        try:
            new_ch = await member.guild.create_voice_channel(name=f"🔊｜{member.display_name}の部屋", category=after.channel.category)
            await member.move_to(new_ch); temp_channels.append(new_ch.id)
            await send_action_log(bot, "🔊 VC作成", f"作成者: {member.mention}")
        except: pass
    if before.channel and before.channel.id in temp_channels and len(before.channel.members) == 0:
        try: await before.channel.delete(); temp_channels.remove(before.channel.id)
        except: pass

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    # スパム防御
    if len(message.mentions) >= 5 or (len(last_messages[message.author.id]) >= 3 and len(set(m["content"] for m in last_messages[message.author.id][-3:])) == 1):
        await message.delete()
        await send_action_log(bot, "🛡 スパム防御", f"実行者: {message.author.mention}", discord.Color.gold())
        return
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
            except: pass
    await bot.process_commands(message)

# --- 7. スラッシュコマンド ---

@bot.tree.command(name="say", description="【管理者】Botが代わりに喋ります")
@app_commands.checks.has_permissions(administrator=True)
async def say(it: discord.Interaction, message: str):
    sent = await it.channel.send(message)
    await it.response.send_message(f"送信完了。修正用ID: `{sent.id}`", ephemeral=True)
    await send_action_log(bot, "💬 Say利用", f"実行者: {it.user.mention}\n内容: {message}\nID: `{sent.id}`")

@bot.tree.command(name="edit", description="【管理者】Botのメッセージを書き換えます")
@app_commands.checks.has_permissions(administrator=True)
async def edit(it: discord.Interaction, message_id: str, new_message: str):
    await it.response.defer(ephemeral=True)
    try:
        msg = await it.channel.fetch_message(int(message_id))
        if msg.author != bot.user: return await it.followup.send("Botのメッセージではありません", ephemeral=True)
        await msg.edit(content=new_message)
        await it.followup.send("書き換え完了", ephemeral=True)
        await send_action_log(bot, "📝 Edit利用", f"実行者: {it.user.mention}\n新内容: {new_message}")
    except: await it.followup.send("見つかりませんでした", ephemeral=True)

@bot.tree.command(name="clear", description="【管理者】メッセージ削除")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(it: discord.Interaction, amount: int):
    await it.response.defer(ephemeral=True)
    deleted = await it.channel.purge(limit=amount)
    await it.followup.send(f"{len(deleted)}件削除しました", ephemeral=True)
    await send_action_log(bot, "🧹 Clear実行", f"実行者: {it.user.mention}\n削除数: {len(deleted)}", discord.Color.purple())

@bot.tree.command(name="ticket_setup", description="【管理者】窓口設置")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_setup(it: discord.Interaction):
    await it.channel.send(embed=discord.Embed(title="📩 お問い合わせ窓口", color=discord.Color.blue()), view=TicketView())
    await it.response.send_message("設置完了", ephemeral=True)

@bot.tree.command(name="ping", description="疎通確認")
async def ping(it: discord.Interaction):
    await it.response.send_message(f"Pong! {round(bot.latency * 1000)}ms", ephemeral=True)

keep_alive()
bot.run(os.getenv('DISCORD_TOKEN'))
