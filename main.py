import discord
from discord.ext import commands
from discord import app_commands
import os
from keep_alive import keep_alive

# 1. 権限（Intents）の設定
intents = discord.Intents.default()
intents.members = True 
intents.message_content = True

bot = commands.Bot(command_prefix='/', intents=intents)

# 通知専用チャンネルID
LOG_CHANNEL_ID = 1475491103225417738 

@bot.event
async def on_ready():
    # スラッシュコマンドを同期
    await bot.tree.sync()
    print(f'ログイン完了: {bot.user.name}')
    
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send("botが起動しました")

# --- /ping コマンド ---
@bot.tree.command(name="ping", description="Botの応答速度を確認します")
async def ping(interaction: discord.Interaction):
    ping_ms = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong! 🏓\n応答速度: {ping_ms}ms")

# --- /say コマンド（管理者限定・隠密モード） ---
@bot.tree.command(name="say", description="【管理者専用】Botに好きな言葉を喋らせます")
@app_commands.describe(message="Botに喋らせたい内容を入力してください")
@app_commands.checks.has_permissions(administrator=True)
async def say(interaction: discord.Interaction, message: str):
    # 本人にだけ確認メッセージを送る
    await interaction.response.send_message("メッセージを送信しました", ephemeral=True)
    # チャンネルに直接メッセージを投稿
    await interaction.channel.send(message)

# --- /say のエラーハンドリング ---
@say.error
async def say_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("このコマンドは管理者さんじゃないと使えないよ…", ephemeral=True)

# --- 参加メッセージ機能 ---
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        guild_name = member.guild.name
        user_name = member.display_name
        message = f"{user_name}さん、こんにちは！「{guild_name}」へようこそ"
        await channel.send(message)

# --- 退出メッセージ機能 ---
@bot.event
async def on_member_remove(member):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        user_name = member.display_name
        message = f"{user_name}さん、さようなら…バイ…バイ…"
        await channel.send(message)

# 2. Webサーバーを起動してBotを動かす
keep_alive()

# Renderの環境変数 "DISCORD_TOKEN" から読み込む設定
# ローカルでテストする場合は直接トークンを書き換えても動きます
TOKEN = os.getenv('DISCORD_TOKEN') or 'YOUR_BOT_TOKEN_HERE'
bot.run(TOKEN)
