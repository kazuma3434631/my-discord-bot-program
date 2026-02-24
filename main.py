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

# --- 2. 設定（指定された全てのIDを反映済み） ---
LOG_CHANNEL_ID = 1475867868724854814      # ログ記録用
WELCOME_CHANNEL_ID = 1475484575114330162  # 参加・退出通知用
TICKET_CATEGORY_ID = 1475853559399452752  # チケット作成先
VC_CREATOR_ID = 1475482867818827829       # VC作成トリガー

# 管理用一時メモリ
last_messages = defaultdict(list)
temp_channels = [] 

# --- 3. UIクラス（役職パネル・チケット） ---

# 役職ボタン
class RoleButton(discord.ui.Button):
    def __init__(self, role: discord.Role):
        super().__init__(label=role.name, style=discord.ButtonStyle.primary, custom_id=f"role_{role.id}")

    async def callback(self, interaction: discord.Interaction):
        role_id = int(self.custom_id.split("_")[1])
        role = interaction.guild.get_role(role_id)
        if not role: return await interaction.response.send_message("役職が見つかりません。", ephemeral=True)
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"役職「{role.name}」を外しました。", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"役職「{role.name}」を付与しました。", ephemeral=True)

# 役職パネル用View
class RolePanelView(discord.ui.View):
    def __init__(self, roles=None):
        super().__init__(timeout=None)
        if roles:
            for role in roles:
                self.add_item(RoleButton(role))

# チケット削除確認
class ConfirmCloseView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="本当に閉じる", style=discord.ButtonStyle.danger, custom_id="confirm_close")
    async def confirm_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.delete()

# チケット内「閉じる」ボタン
class CloseTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="チケットを閉じる", style=discord.ButtonStyle.secondary, emoji="🔒", custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("このチケットを閉じてもよろしいですか？", view=ConfirmCloseView(), ephemeral=True)

# 窓口View
class TicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    async def create_ticket_logic(self, interaction: discord.Interaction, ticket_type: str, color: discord.Color):
        guild, user = interaction.guild, interaction.user
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        category = guild.get_channel(TICKET_CATEGORY_ID)
        channel = await guild.create_text_channel(name=f"{ticket_type}-{user.display_name}", overwrites=overwrites, category=category)
        await interaction.response.send_message(f"チケットを作成しました: {channel.mention}", ephemeral=True)
        embed = discord.Embed(title=f"【{ticket_type}】", description=f"{user.mention} さん、内容を記入してください。", color=color)
        await channel.send(embed=embed, view=CloseTicketView())

    @discord.ui.button(label="🚨 通報", style=discord.ButtonStyle.danger, custom_id="ticket_report")
    async def report(self, it): await self.create_ticket_logic(it, "通報", discord.Color.red())
    @discord.ui.button(label="❓ 質問", style=discord.ButtonStyle.primary, custom_id="ticket_question")
    async def question(self, it): await self.create_ticket_logic(it, "質問", discord.Color.blue())
    @discord.ui.button(label="💡 提案", style=discord.ButtonStyle.success, custom_id="ticket_suggest")
    async def suggest(self, it): await self.create_ticket_logic(it, "提案", discord.Color.green())

# --- 4. Bot本体 ---
class MyBot(commands.Bot):
    def __init__(self): super().__init__(command_prefix='/', intents=intents)
    async def setup_hook(self):
        # 永続的なViewを登録
        self.add_view(TicketView()); self.add_view(CloseTicketView()); self.add_view(ConfirmCloseView())
        self.add_view(RolePanelView())
        await self.tree.sync()

bot = MyBot()

# --- 5. イベント処理 ---

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    log = bot.get_channel(LOG_CHANNEL_ID)
    if log: await log.send("✅ **Bot完全版 起動完了**\n全てのセキュリティ・管理システムが正常に動作しています。")

# ボイスチャット自動作成
@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and after.channel.id == VC_CREATOR_ID:
        new_ch = await member.guild.create_voice_channel(name=f"🔊｜{member.display_name}の部屋", category=after.channel.category)
        await member.move_to(new_ch); temp_channels.append(new_ch.id)
    if before.channel and before.channel.id in temp_channels and len(before.channel.members) == 0:
        try: await before.channel.delete(); temp_channels.remove(before.channel.id)
        except: pass

# メッセージ管理（荒らし対策・リンク展開）
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return

    # 大量メンション対策
    if len(message.mentions) >= 5:
        await message.delete(); await message.channel.send(f"{message.author.mention} 大量メンションはやめてね", delete_after=5); return

    # 連投対策
    u_id, now = message.author.id, datetime.datetime.now()
    last_messages[u_id].append({"content": message.content, "time": now})
    last_messages[u_id] = [m for m in last_messages[u_id] if (now - m["time"]).total_seconds() < 5]
    if len(last_messages[u_id]) >= 3 and len(set(m["content"] for m in last_messages[u_id][-3:])) == 1:
        await message.delete(); await message.channel.send(f"{message.author.mention} 連投を検知し削除しました。", delete_after=5); return

    # メッセージリンク展開
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

# ログ出力（削除・編集）
@bot.event
async def on_message_delete(message):
    if message.author.bot: return
    log = bot.get_channel(LOG_CHANNEL_ID)
    if log:
        emb = discord.Embed(title="🗑 削除ログ", color=discord.Color.red(), timestamp=message.created_at)
        emb.add_field(name="投稿者", value=message.author.mention); emb.add_field(name="内容", value=message.content or "なし"); await log.send(embed=emb)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content: return
    log = bot.get_channel(LOG_CHANNEL_ID)
    if log:
        emb = discord.Embed(title="📝 編集ログ", color=discord.Color.orange(), timestamp=after.edited_at)
        emb.add_field(name="前", value=before.content); emb.add_field(name="後", value=after.content); await log.send(embed=emb)

# 参加退出通知
@bot.event
async def on_member_join(member):
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if ch: await ch.send(f"{member.display_name}さん、いらっしゃい！")

@bot.event
async def on_member_remove(member):
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if ch: await ch.send(f"{member.display_name}さんが旅立ちました。")

# --- 6. スラッシュコマンド ---

@bot.tree.command(name="role_setup", description="新規役職パネルを設置")
@app_commands.checks.has_permissions(administrator=True)
async def role_setup(it, title: str, role1: discord.Role):
    view = RolePanelView([role1])
    await it.channel.send(embed=discord.Embed(title=title, color=discord.Color.green()), view=view)
    await it.response.send_message("設置完了。追加は `/role_add` を使用してください。", ephemeral=True)

@bot.tree.command(name="role_add", description="既存のパネルにボタンを追加")
@app_commands.checks.has_permissions(administrator=True)
async def role_add(it, message_id: str, role: discord.Role):
    await it.response.defer(ephemeral=True)
    try:
        msg = await it.channel.fetch_message(int(message_id))
        view = RolePanelView()
        if msg.components:
            for row in msg.components:
                for comp in row.children:
                    if comp.custom_id == f"role_{role.id}": return await it.followup.send("既に追加済みです", ephemeral=True)
                    r_id = int(comp.custom_id.split("_")[1]); r_obj = it.guild.get_role(r_id)
                    if r_obj: view.add_item(RoleButton(r_obj))
        view.add_item(RoleButton(role))
        await msg.edit(view=view); await it.followup.send(f"✅ {role.name}を追加しました", ephemeral=True)
    except Exception as e: await it.followup.send(f"❌ エラー: {e}", ephemeral=True)

@bot.tree.command(name="ticket_setup", description="窓口設置")
async def ticket_setup(it):
    await it.channel.send(embed=discord.Embed(title="📩 お問い合わせ窓口", color=discord.Color.blue()), view=TicketView())
    await it.response.send_message("完了", ephemeral=True)

@bot.tree.command(name="clear", description="一括削除")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(it, amount: int):
    await it.response.defer(ephemeral=True)
    deleted = await it.channel.purge(limit=amount)
    await it.followup.send(f"✅ {len(deleted)}件削除しました", ephemeral=True)

@bot.tree.command(name="say", description="代弁")
@app_commands.checks.has_permissions(administrator=True)
async def say(it, message: str):
    await it.channel.send(message); await it.response.send_message("送信", ephemeral=True)

@bot.tree.command(name="ping", description="疎通確認")
async def ping(it): await it.response.send_message(f"Pong! {round(bot.latency * 1000)}ms", ephemeral=True)

# 実行
keep_alive()
bot.run(os.getenv('DISCORD_TOKEN'))
