import re
import os
import json
import datetime
import psycopg2
import discord
from discord.ext import commands
from psycopg2 import sql

TOKEN = os.environ["TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)


class Boring:
    courses_list = ["135", "202", "218", "219", "370"]
    thank_you_list = ["THANK YOU", "THANKS"]
    conn = None
    cur = None

    @bot.event
    async def on_guild_join(guild):
        if discord.utils.get(guild.categories, name="Server Stats") is None:
            category = await guild.create_category(name="Server Stats")
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False)
            }
            await guild.create_voice_channel(
                name=(f"Member Count: {guild.member_count}"),
                overwrites=overwrites,
                category=category,
            )
        if discord.utils.get(guild.categories, name="Tickets") is None:
            category = await guild.create_category(name="Tickets")

        try:
            Boring.cur.execute(
                sql.SQL(
                    "CREATE TABLE IF NOT EXISTS {} (name VARCHAR(255) NOT NULL, karma INTEGER, UNIQUE(name))"
                ).format(sql.Identifier(guild.name))
            )
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            try:
                Boring.conn = psycopg2.connect(DATABASE_URL, sslmode="require")
                Boring.conn.autocommit = True
                Boring.cur = Boring.conn.cursor()
            except (Exception, psycopg2.DatabaseError) as conErr:
                print(conErr)
        finally:
            print(f"Database Table for {guild.name} setup!")

    @bot.event
    async def on_member_join(member):
        guild = member.guild
        student_role = discord.utils.get(guild.roles, name="Student")
        await discord.Member.add_roles(member, student_role)

        channel = discord.utils.get(
            guild.voice_channels, name=(
                f"Member Count: {guild.member_count - 1}")
        )
        if channel:
            await channel.edit(name=(f"Member Count: {guild.member_count}"))

    @bot.event
    async def on_member_remove(member):
        guild = member.guild
        channel = discord.utils.get(
            guild.voice_channels, name=(
                f"Member Count: {guild.member_count + 1}")
        )
        if channel:
            await channel.edit(name=(f"Member Count: {guild.member_count}"))

    @bot.event
    async def on_message(message):
        if message.author == bot.user:
            return

        content = message.content.upper()
        for check in Boring.thank_you_list:
            if content.find(check) > -1:
                for i in message.mentions:
                    if i != message.author and i != bot.user:
                        try:
                            name = i.name + i.discriminator
                            guild = message.author.guild
                            Boring.cur.execute(
                                sql.SQL(
                                    "INSERT INTO {table} (name, karma) VALUES (%s, %s) ON CONFLICT (name) DO UPDATE SET karma = {table}.karma + 1;"
                                ).format(table=sql.Identifier(guild.name)),
                                [name, 1],
                            )
                        except (Exception, psycopg2.DatabaseError) as error:
                            print(error)
                            try:
                                Boring.conn = psycopg2.connect(
                                    DATABASE_URL, sslmode="require"
                                )
                                Boring.conn.autocommit = True
                                Boring.cur = Boring.conn.cursor()
                            except (Exception, psycopg2.DatabaseError) as conErr:
                                print(conErr)
                        finally:
                            await message.channel.send(f"Gave +1 Karma to {i.mention}")
                break
        await bot.process_commands(message)

    @bot.event
    async def on_ready():
        print(f"Logged in as {bot.user.name}")

    @bot.command()
    async def clear(ctx, count=0):
        if ctx.message.author.guild_permissions.administrator:
            await ctx.channel.purge(limit=count + 1)
        else:
            await ctx.send(
                "You do not have the necessary permissions to clear messages!"
            )

    @bot.command()
    async def close(ctx):
        guild = ctx.message.guild
        member = ctx.message.author
        member_roles = member.roles
        ta_role = discord.utils.get(guild.roles, name="TA")

        if ta_role in member_roles:
            if ctx.message.channel.name.find("ticket") > -1:
                messages = await ctx.message.channel.history(limit=999).flatten()
                get_user_str = messages[-1].embeds[0].description.split("\n")
                user_id = int(re.sub("[^0-9]", "", get_user_str[0]))
                send_to = guild.get_member(user_id)
                with open("ticket.txt", "w") as file:
                    for message in reversed(messages):
                        file.write(
                            f"User: {message.author.name} -> {message.content}\n"
                        )
                with open("ticket.txt", "rb") as file:
                    dm_channel = await send_to.create_dm()
                    await dm_channel.send(
                        "Your ticket has been closed, attached is the ticket history:",
                        file=discord.File(file, "ticket.txt"),
                    )
                await ctx.message.channel.delete()
            else:
                await ctx.send("Unable to close, this is not a ticket!")
        else:
            await ctx.send(
                "You do not have the necessary permissions to close a ticket!"
            )

    @bot.command()
    async def courses(ctx):
        await ctx.send(f"Course Number Options:  `135`  `202`  `218`  `219`  `370`")

    @bot.command()
    async def embed(ctx, *, message):
        if ctx.message.author.guild_permissions.administrator:
            color = 0xCF65E7
            data = None
            desc = None
            title = None

            try:
                data = json.loads(message)
            except:
                await ctx.send("`embed`: Error, JSON format invalid!")
                return

            try:
                title = data["title"]
            except:
                await ctx.send("`embed`: Error, no title provided!")
                return

            if "description" in data:
                desc = data["description"]

            if "color" in data:
                color = data["color"]

            ce = discord.Embed(
                title=title,
                description=desc,
                color=color,
            )

            if "fields" in data:
                for field in data["fields"]:
                    ce.add_field(name=field["name"],
                                 value=field["value"], inline=False)

            if await ctx.send(embed=ce):
                await ctx.message.delete()
        else:
            await ctx.send(
                "You do not have the necessary permissions to create an embed!"
            )

    @bot.command()
    async def leaderboard(ctx):
        karma_dict = None
        member = ctx.author
        try:
            Boring.cur.execute(
                sql.SQL("SELECT * FROM {} ORDER BY karma DESC;").format(
                    sql.Identifier(member.guild.name)
                )
            )
            karma_dict = Boring.cur.fetchall()
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            try:
                Boring.conn = psycopg2.connect(DATABASE_URL, sslmode="require")
                Boring.conn.autocommit = True
                Boring.cur = Boring.conn.cursor()
            except (Exception, psycopg2.DatabaseError) as conErr:
                print(conErr)

        leaders_embed = discord.Embed(
            title=f"Top 10 Most Helpful People",
            color=0xFFED06,
        )
        pos = 0
        for entry in karma_dict:
            leaders_embed.add_field(
                name=f"{pos+1}. {entry[0]}", value=f"{entry[1]} karma", inline=False
            )
            pos += 1
            if pos == 10:
                break
        await ctx.send(embed=leaders_embed)

    @bot.command()
    async def profile(ctx, member: discord.Member = None):
        roles = ""
        member = member or ctx.author
        name = member.name + member.discriminator
        karma = 0
        try:
            Boring.cur.execute(
                sql.SQL("SELECT karma FROM {} WHERE name = %s").format(
                    sql.Identifier(member.guild.name)
                ),
                [name],
            )
            karma = Boring.cur.fetchone()
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)
            try:
                Boring.conn = psycopg2.connect(DATABASE_URL, sslmode="require")
                Boring.conn.autocommit = True
                Boring.cur = Boring.conn.cursor()
            except (Exception, psycopg2.DatabaseError) as conErr:
                print(conErr)
        finally:
            if karma:
                karma = karma[0]
            else:
                karma = 0

        join_date = member.joined_at
        join_date = f"{join_date.month}/{join_date.day}/{join_date.year}"
        for role in member.roles[:-1]:
            if role.name != "@everyone":
                roles += role.name + ", "
        roles += member.roles[-1].name

        profile_embed = discord.Embed(
            title=f"Profile of {member.name}",
            description="Karma Profile",
            color=0x50E3C2,
        )
        profile_embed.set_thumbnail(url=member.avatar_url)
        profile_embed.add_field(name="Karma", value=karma, inline=False)
        profile_embed.add_field(
            name="Date Joined", value=join_date, inline=True)
        profile_embed.add_field(name="Roles", value=roles, inline=True)
        await ctx.send(embed=profile_embed)

    @bot.command()
    async def send(ctx, *, message):
        if ctx.message.author.guild_permissions.administrator:
            if await ctx.send(message):
                await ctx.message.delete()
        else:
            await ctx.send(
                "You do not have the necessary permissions to create an send a message!"
            )

    @bot.command()
    async def ticket(ctx, course="default"):
        guild = ctx.message.guild
        request_channel = discord.utils.get(guild.channels, name="request")
        if ctx.message.channel != request_channel:
            failed_embed = discord.Embed(
                title="Failed to create a ticket",
                description=f"Ticket must be created in {request_channel.mention}!",
                color=0xE73C24,
            )
            await ctx.send(embed=failed_embed)
            return
        if str(course) in Boring.courses_list:
            if discord.utils.get(
                guild.channels,
                name=(f"ticket-{course}-{ctx.message.author.name.lower()}"),
            ):
                failed_embed = discord.Embed(
                    title="Failed to create a ticket",
                    description="You already have a ticket open, please don't try to open a ticket while you already have one.",
                    color=0xE73C24,
                )
                await ctx.send(embed=failed_embed)
            else:
                category = discord.utils.get(guild.categories, name="Tickets")
                ta = discord.utils.get(guild.roles, name=course)
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(
                        read_messages=False
                    ),
                    ctx.message.author: discord.PermissionOverwrite(read_messages=True),
                    ta: discord.PermissionOverwrite(read_messages=True),
                }
                ticket_create = await guild.create_text_channel(
                    name=(f"ticket-{course}-{ctx.message.author.name}"),
                    overwrites=overwrites,
                    category=category,
                )
                ticket_embed = discord.Embed(
                    title="Ticket",
                    description=(
                        f"{ctx.message.author.mention}\nPlease ask your question and a TA will be with you shortly."
                    ),
                    color=0x15A513,
                )
                ticket_embed.set_footer(
                    text=(f"Ticket requested by {ctx.message.author}"),
                    icon_url=ctx.message.author.avatar_url,
                )
                await ticket_create.send(embed=ticket_embed)
                success_embed = discord.Embed(
                    title="Ticket Creation",
                    description=(
                        f"{ctx.message.author.mention}, your ticket was successfully created: {ticket_create.mention}"
                    ),
                    color=0x15A513,
                )
                await ctx.send(embed=success_embed)
        else:
            await ctx.send(
                f"`!ticket <course number>`\n\nInvalid course number, refer to `!courses`"
            )

    def main():
        Boring.conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        Boring.conn.autocommit = True
        Boring.cur = Boring.conn.cursor()
        bot.run(TOKEN)


if __name__ == "__main__":
    Boring.main()
