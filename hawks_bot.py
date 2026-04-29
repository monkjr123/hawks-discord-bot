import os
import requests
import discord
import feedparser
from discord.ext import tasks, commands
from discord import app_commands
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

FEEDS = [
    "https://www.espn.com/espn/rss/nba/news",
    "https://www.cbssports.com/rss/headlines/nba/",
    "https://sports.yahoo.com/nba/rss/",
    "https://www.peachtreehoops.com/rss/current",
    "https://www.si.com/nba/hawks/rss",
]

KEYWORDS = [
    "hawks",
    "atlanta hawks",
    "atlanta",
    "trae young",
    "jalen johnson",
    "dyson daniels",
    "zaccharie risacher",
    "risacher",
    "onyeka okongwu",
    "okongwu",
    "nba draft",
    "trade",
    "injury",
]

URGENT_KEYWORDS = [
    "trade",
    "traded",
    "signs",
    "signed",
    "waived",
    "injury",
    "injured",
    "out",
    "questionable",
    "doubtful",
    "surgery",
    "extension",
    "contract",
    "breaking",
]

posted_links = set()
posted_game_alerts = set()


def get_hawks_news(limit=6):
    urgent_news = []
    normal_news = []

    for feed_url in FEEDS:
        feed = feedparser.parse(feed_url)

        for entry in feed.entries:
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "")
            published = entry.get("published", "")

            text = f"{title} {summary}".lower()

            if not link or link in posted_links:
                continue

            if any(keyword in text for keyword in KEYWORDS):
                item = {
                    "title": title,
                    "link": link,
                    "summary": summary[:275] if summary else "Tap the title to read the full story.",
                    "published": published,
                }

                if any(word in text for word in URGENT_KEYWORDS):
                    urgent_news.append(item)
                else:
                    normal_news.append(item)

                posted_links.add(link)

    return urgent_news[:limit], normal_news[:limit]


def get_hawks_games():
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"

    try:
        data = requests.get(url, timeout=10).json()
    except Exception:
        return []

    games = []

    for event in data.get("events", []):
        competition = event.get("competitions", [{}])[0]
        competitors = competition.get("competitors", [])

        teams = [c.get("team", {}).get("abbreviation") for c in competitors]

        if "ATL" not in teams:
            continue

        game_id = event.get("id")
        event_date = event.get("date")
        status_type = event.get("status", {}).get("type", {})
        status_name = status_type.get("description", "Unknown")
        short_status = status_type.get("shortDetail", "No status available")

        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)

        if not home or not away:
            continue

        games.append({
            "id": game_id,
            "date": event_date,
            "status": status_name,
            "short_status": short_status,
            "home": home["team"]["displayName"],
            "away": away["team"]["displayName"],
            "home_abbr": home["team"]["abbreviation"],
            "away_abbr": away["team"]["abbreviation"],
            "home_score": home.get("score", "0"),
            "away_score": away.get("score", "0"),
        })

    return games


def make_news_embed(item, urgent=False):
    embed = discord.Embed(
        title=item["title"],
        url=item["link"],
        description=item["summary"],
        color=discord.Color.red() if urgent else discord.Color.from_rgb(225, 68, 52),
    )

    embed.set_author(name="Atlanta Hawks News Bot")

    embed.add_field(
        name="Category",
        value="🚨 Breaking / Trade / Injury Alert" if urgent else "🏀 Hawks News",
        inline=False,
    )

    if item.get("published"):
        embed.add_field(name="Published", value=item["published"], inline=False)

    embed.set_footer(text="Powered by Hawks Discord Bot")
    return embed


def make_game_embed(game):
    embed = discord.Embed(
        title=f"{game['away']} @ {game['home']}",
        description=game["short_status"],
        color=discord.Color.from_rgb(225, 68, 52),
    )

    embed.add_field(
        name="Score",
        value=f"**{game['away_abbr']}**: {game['away_score']}\n**{game['home_abbr']}**: {game['home_score']}",
        inline=False,
    )

    embed.add_field(name="Status", value=game["status"], inline=False)
    embed.set_footer(text="Atlanta Hawks Game Tracker")
    return embed


class HawksDashboard(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Refresh News", style=discord.ButtonStyle.danger, emoji="📰")
    async def refresh_news(self, interaction: discord.Interaction, button: discord.ui.Button):
        urgent_news, normal_news = get_hawks_news()
        all_news = urgent_news + normal_news

        if not all_news:
            await interaction.response.send_message("No fresh Hawks news found right now.", ephemeral=True)
            return

        await interaction.response.send_message("📰 Latest Hawks news:", ephemeral=True)

        for item in all_news[:5]:
            await interaction.followup.send(embed=make_news_embed(item, item in urgent_news), ephemeral=True)

    @discord.ui.button(label="Game Updates", style=discord.ButtonStyle.primary, emoji="🏀")
    async def game_updates(self, interaction: discord.Interaction, button: discord.ui.Button):
        games = get_hawks_games()

        if not games:
            await interaction.response.send_message("No Hawks game found on today’s ESPN scoreboard.", ephemeral=True)
            return

        await interaction.response.send_message("🏀 Hawks game updates:", ephemeral=True)

        for game in games:
            await interaction.followup.send(embed=make_game_embed(game), ephemeral=True)

    @discord.ui.button(label="Help", style=discord.ButtonStyle.secondary, emoji="❓")
    async def help_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        message = """
**Hawks Bot Commands**

`/hawks` — Full dashboard  
`/news` — Latest Hawks news  
`/games` — Hawks game status  
`/helpme` — Show help menu  

The bot also automatically checks:
🚨 urgent trade/injury news every 5 minutes  
🏀 games every 10 minutes  
📰 daily news roundup every 24 hours
"""
        await interaction.response.send_message(message, ephemeral=True)


async def send_dashboard(channel):
    embed = discord.Embed(
        title="🏀 Atlanta Hawks Command Center",
        description="Use the buttons below or slash commands to check Hawks news, games, injuries, trades, and updates.",
        color=discord.Color.from_rgb(225, 68, 52),
    )

    embed.add_field(
        name="Live Features",
        value="🚨 Trade/Injury alerts\n🏀 Game updates\n📰 Daily roundup\n🔁 Manual refresh buttons",
        inline=False,
    )

    embed.set_footer(text="Hawks Bot is live 24/7")
    await channel.send(embed=embed, view=HawksDashboard())


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"Slash command sync failed: {e}")

    channel = await bot.fetch_channel(CHANNEL_ID)

    await channel.send("✅ Hawks bot is online and upgraded.")
    await send_dashboard(channel)

    if not urgent_news_check.is_running():
        urgent_news_check.start()

    if not daily_news_check.is_running():
        daily_news_check.start()

    if not game_check.is_running():
        game_check.start()


@tasks.loop(minutes=5)
async def urgent_news_check():
    channel = await bot.fetch_channel(CHANNEL_ID)
    urgent_news, _ = get_hawks_news()

    for item in urgent_news:
        await channel.send("🚨 **Hawks Alert**")
        await channel.send(embed=make_news_embed(item, urgent=True))


@tasks.loop(hours=24)
async def daily_news_check():
    channel = await bot.fetch_channel(CHANNEL_ID)
    _, normal_news = get_hawks_news()

    if not normal_news:
        return

    await channel.send("📰 **Daily Atlanta Hawks News Roundup**")

    for item in normal_news[:5]:
        await channel.send(embed=make_news_embed(item))


@tasks.loop(minutes=10)
async def game_check():
    channel = await bot.fetch_channel(CHANNEL_ID)
    games = get_hawks_games()

    for game in games:
        post_key = f"{game['id']}-{game['status']}-{game['away_score']}-{game['home_score']}"

        if post_key in posted_game_alerts:
            continue

        posted_game_alerts.add(post_key)

        if game["status"] in ["Scheduled", "In Progress", "Final"]:
            await channel.send("🏀 **Hawks Game Update**")
            await channel.send(embed=make_game_embed(game))


@bot.tree.command(name="hawks", description="Open the Atlanta Hawks command center.")
async def hawks_slash(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🏀 Atlanta Hawks Command Center",
        description="Use the buttons below to check news, games, trades, injuries, and alerts.",
        color=discord.Color.from_rgb(225, 68, 52),
    )

    await interaction.response.send_message(embed=embed, view=HawksDashboard())


@bot.tree.command(name="news", description="Get the latest Atlanta Hawks news.")
async def news_slash(interaction: discord.Interaction):
    urgent_news, normal_news = get_hawks_news()
    all_news = urgent_news + normal_news

    if not all_news:
        await interaction.response.send_message("No fresh Hawks news found right now.")
        return

    await interaction.response.send_message("📰 Latest Hawks news:")

    for item in all_news[:5]:
        await interaction.followup.send(embed=make_news_embed(item, item in urgent_news))


@bot.tree.command(name="games", description="Get the current Atlanta Hawks game update.")
async def games_slash(interaction: discord.Interaction):
    games = get_hawks_games()

    if not games:
        await interaction.response.send_message("No Hawks game found on today’s ESPN scoreboard.")
        return

    await interaction.response.send_message("🏀 Hawks game update:")

    for game in games:
        await interaction.followup.send(embed=make_game_embed(game))


@bot.tree.command(name="helpme", description="Show Hawks bot help.")
async def help_slash(interaction: discord.Interaction):
    message = """
**Hawks Bot Help**

`/hawks` — Open interactive dashboard  
`/news` — Latest Hawks news  
`/games` — Current Hawks game status  
`/helpme` — Show this menu  

Automatic alerts:
🚨 Trade/injury checks every 5 minutes  
🏀 Game checks every 10 minutes  
📰 Daily roundup every 24 hours
"""
    await interaction.response.send_message(message)


bot.run(TOKEN)