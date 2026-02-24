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

# --- 2. 設定（指定された全てのIDを反映） ---
LOG_CHANNEL_ID = 1475867868724854814      # ログ記録用
WELCOME_CHANNEL_ID = 1475484575114330162  # 参加・退出通知用
TICKET_CATEGORY_ID = 1475853559399452752  # チケット作成先
VC_CREATOR_ID = 1475482867818827829       # VC作成トリガー

# 管理用一時メモリ
last_messages = defaultdict(list)
temp_channels = [] 

# --- 3. UIクラス（役職パネル・チケット） ---

# 役職ボタンの個別クラス
class RoleButton(discord.ui.Button):
    def __init__(self, role: discord.Role):
        super().__init__(label=role.name, style=discord.ButtonStyle.primary, custom_id=f"role_{role.id}")

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(int(self.custom_id.split("_")[1]))
        if not role: return await interaction.response.send_message("役職が見つかりません。", ephemeral=True)
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"役職「{role.name}」を外しました。", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"役職「{role.name}」を付与しました。", ephemeral=True)

class RolePanelView(discord.ui.View):
    def __init__(self, roles):
        super().__init__(timeout=None)
        for role in roles: self.add_item(RoleButton(role))

# チケット削除確認
class ConfirmCloseView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="本当に閉じる", style=discord.ButtonStyle.danger, custom_id="confirm_close")
    async def confirm_close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.delete()

class CloseTicketView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="チケットを閉じる", style=discord.ButtonStyle.secondary, emoji="🔒", custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("このチケットを閉じてもよろしいですか？", view=ConfirmCloseView(), ephemeral=True)

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
    async def report_ticket(self, interaction: discord.Interaction, button: discord.ui.Button): await self.create_ticket_logic(interaction, "通報", discord.Color.red())
    @discord.ui.button(label="❓ 質問", style=discord.ButtonStyle.primary, custom_id="ticket_question")
    async def question_ticket(self, interaction: discord.Interaction, button: discord.ui.Button): await self.create_ticket_logic(interaction, "質問", discord.Color.blue())
    @discord.ui.button(label="💡 提案", style=discord.ButtonStyle.success, custom_id="ticket_suggest")
    async def suggest_ticket(self, interaction: discord.Interaction, button: discord.ui.Button): await self.create_ticket_logic(interaction, "提案", discord.Color.green())

# --- 4. Botクラス ---
class MyBot(commands.Bot):
    def __init__(self): super().__init__(command_prefix='/', intents=intents)
    async def setup_hook(self):
        self.add_view(TicketView()); self.add_view(CloseTicketView()); self.add_view(ConfirmCloseView())
        await self.tree.sync()

bot = MyBot()

# --- 5. イベント処理 ---

@bot.event
async def on_ready():
    print(f'ログイン: {bot.user.name}')
    log = bot.get_channel(LOG_CHANNEL_ID)
    if log: await log.send("✅ **システムオンライン**\n全ての管理・防衛機能が有効です。")

# VC自動作成・削除
@bot.event
async def on_voice_state_update(member, before, after):
    if after.channel and after.channel.id == VC_CREATOR_ID:
        new_channel = await member.guild.create_voice_channel(name=f"🔊｜{member.display_name}の部屋", category=after.channel.category)
        await member.move_to(new_channel)
        temp_channels.append(new_channel.id)
    if before.channel and before.channel.id in temp_channels and len(before.channel.members) == 0:
        await before.channel.delete()
        temp_channels.remove(before.channel.id)

# メッセージ処理（荒らし対策・リンク展開）
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return

    # 大量メンション対策
    if len(message.mentions) >= 5:
        await message.delete()
        await message.channel.send(f"{message.author.mention} 大量メンションはやめてね", delete_after=5)
        return

    # 連投対策
    user_id, now = message.author.id, datetime.datetime.now()
    user_msgs = last_messages[user_id]
    user_msgs.append({"content": message.content, "time": now})
    last_messages[user_id] = [m for m in user_msgs if (now - m["time"]).total_seconds() < 5]
    if len(last_messages[user_id]) >= 3 and len(set(m["content"] for m in last_messages[user_id][-3:])) == 1:
        await message.delete()
        await message.channel.send(f"{message.author.mention} 連投を検知し削除しました。", delete_after=5)
        return

    # リンク展開
    extract = re.search(r"https://(?:ptb\.|canary\.)?discord\.com/channels/(\d+)/(\d+)/(\d+)", message.content)
    if extract:
        g_id, c_id, m_id = map(int, extract.groups())
        if message.guild.id == g_id:
            try:
                f_msg = await bot.get_channel(c_id).fetch_message(m_id)
                emb = discord.Embed(description=f_msg.content, color=discord.Color.light_grey(), timestamp=f_msg.created_at)
                emb.set_author(name=f_msg.author.display_name, icon_url=f_msg.author.display_avatar.url)
                if f_msg.attachments: emb.set_image(url=f_msg.attachments[0].url)
                await message.reply(embed=emb, mention_author=False)
            except: pass
    await bot.process_commands(message)

# 削除・編集ログ
@bot.event
async def on_message_delete(message):
    if message.author.bot: return
    log = bot.get_channel(LOG_CHANNEL_ID)
    if log:
        emb = discord.Embed(title="🗑 削除", color=discord.Color.red(), timestamp=message.created_at)
        emb.add_field(name="人", value=message.author.mention); emb.add_field(name="内容", value=message.content or "なし")
        await log.send(embed=emb)

@bot.event
async def on_message_edit(before, after):
    if before.author.bot or before.content == after.content: return
    log = bot.get_channel(LOG_CHANNEL_ID)
    if log:
        emb = discord.Embed(title="📝 編集", color=discord.Color.orange(), timestamp=after.edited_at)
        emb.add_field(name="人", value=before.author.mention)
        emb.add_field(name="前", value=before.content); emb.add_field(name="後", value=after.content)
        await log.send(embed=emb)

# 参加退出
@bot.event
async def on_member_join(member):
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if ch: await ch.send(f"{member.display_name}さん、ようこそ！")

@bot.event
async def on_member_remove(member):
    ch = bot.get_channel(WELCOME_CHANNEL_ID)
    if ch: await ch.send(f"{member.display_name}さんが退出しました。")

# --- 6. スラッシュコマンド ---

@bot.tree.command(name="role_setup", description="役職付与パネルを設置")
@app_commands.checks.has_permissions(administrator=True)
async def role_setup(interaction: discord.Interaction, title: str, role1: discord.Role, role2: discord.Role = None, role3: discord.Role = None):
    roles = [r for r in [role1, role2, role3] if r]
    await interaction.channel.send(embed=discord.Embed(title=title, color=discord.Color.green()), view=RolePanelView(roles))
    await interaction.response.send_message("設置完了", ephemeral=True)

@bot.tree.command(name="ticket_setup", description="窓口設置")
async def ticket_setup(interaction: discord.Interaction):
    await interaction.channel.send(embed=discord.Embed(title="📩 窓口", color=discord.Color.blue()), view=TicketView())
    await interaction.response.send_message("設置完了", ephemeral=True)

@bot.tree.command(name="clear", description="一括削除")
async def clear(interaction: discord.Interaction, amount: int, user: discord.Member = None):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount, check=lambda m: user is None or m.author == user)
    await interaction.followup.send(f"✅ {len(deleted)}件削除", ephemeral=True)

@bot.tree.command(name="say", description="Botに喋らせる")
async def say(interaction: discord.Interaction, message: str):
    await interaction.channel.send(message)
    await interaction.response.send_message("送信完了", ephemeral=True)

@bot.tree.command(name="edit", description="Botの発言を修正")
async def edit(interaction: discord.Interaction, message_id: str, new_text: str):
    try:
        msg = await interaction.channel.fetch_message(int(message_id))
        await msg.edit(content=new_text)
        await interaction.response.send_message("✅ 修正完了", ephemeral=True)
    except: await interaction.response.send_message("❌ 失敗", ephemeral=True)

# 実行
keep_alive()
bot.run(os.getenv('DISCORD_TOKEN'))
