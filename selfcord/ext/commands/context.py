# -*- coding: utf-8 -*-

"""
The MIT License (MIT)

Copyright (c) 2015-present Rapptz

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

import selfcord.abc
import selfcord.utils

class Context(selfcord.abc.Messageable):
    r"""Represents the context in which a command is being invoked under.

    This class contains a lot of meta data to help you understand more about
    the invocation context. This class is not created manually and is instead
    passed around to commands as the first parameter.

    This class implements the :class:`~selfcord.abc.Messageable` ABC.

    Attributes
    -----------
    message: :class:`.Message`
        The message that triggered the command being executed.
    bot: :class:`.Bot`
        The bot that contains the command being executed.
    args: :class:`list`
        The list of transformed arguments that were passed into the command.
        If this is accessed during the :func:`on_command_error` event
        then this list could be incomplete.
    kwargs: :class:`dict`
        A dictionary of transformed arguments that were passed into the command.
        Similar to :attr:`args`\, if this is accessed in the
        :func:`on_command_error` event then this dict could be incomplete.
    prefix: :class:`str`
        The prefix that was used to invoke the command.
    command: :class:`Command`
        The command that is being invoked currently.
    invoked_with: :class:`str`
        The command name that triggered this invocation. Useful for finding out
        which alias called the command.
    invoked_parents: List[:class:`str`]
        The command names of the parents that triggered this invocation. Useful for
        finding out which aliases called the command.

        For example in commands ``?a b c test``, the invoked parents are ``['a', 'b', 'c']``.

        .. versionadded:: 1.7

    invoked_subcommand: :class:`Command`
        The subcommand that was invoked.
        If no valid subcommand was invoked then this is equal to ``None``.
    subcommand_passed: Optional[:class:`str`]
        The string that was attempted to call a subcommand. This does not have
        to point to a valid registered subcommand and could just point to a
        nonsense string. If nothing was passed to attempt a call to a
        subcommand then this is set to ``None``.
    command_failed: :class:`bool`
        A boolean that indicates if the command failed to be parsed, checked,
        or invoked.
    """

    def __init__(self, **attrs):
        self.message = attrs.pop('message', None)
        self.bot = attrs.pop('bot', None)
        self.args = attrs.pop('args', [])
        self.kwargs = attrs.pop('kwargs', {})
        self.prefix = attrs.pop('prefix')
        self.command = attrs.pop('command', None)
        self.view = attrs.pop('view', None)
        self.invoked_with = attrs.pop('invoked_with', None)
        self.invoked_parents = attrs.pop('invoked_parents', [])
        self.invoked_subcommand = attrs.pop('invoked_subcommand', None)
        self.subcommand_passed = attrs.pop('subcommand_passed', None)
        self.command_failed = attrs.pop('command_failed', False)
        self._state = self.message._state

    async def invoke(self, *args, **kwargs):
        r"""|coro|

        Calls a command with the arguments given.

        This is useful if you want to just call the callback that a
        :class:`.Command` holds internally.

        .. note::

            This does not handle converters, checks, cooldowns, pre-invoke,
            or after-invoke hooks in any matter. It calls the internal callback
            directly as-if it was a regular function.

            You must take care in passing the proper arguments when
            using this function.

        .. warning::

            The first parameter passed **must** be the command being invoked.

        Parameters
        -----------
        command: :class:`.Command`
            The command that is going to be called.
        \*args
            The arguments to to use.
        \*\*kwargs
            The keyword arguments to use.

        Raises
        -------
        TypeError
            The command argument to invoke is missing.
        """

        try:
            command = args[0]
        except IndexError:
            raise TypeError('Missing command to invoke.') from None

        arguments = []
        if command.cog is not None:
            arguments.append(command.cog)

        arguments.append(self)
        arguments.extend(args[1:])

        ret = await command.callback(*arguments, **kwargs)
        return ret

    async def reinvoke(self, *, call_hooks=False, restart=True):
        """|coro|

        Calls the command again.

        This is similar to :meth:`~.Context.invoke` except that it bypasses
        checks, cooldowns, and error handlers.

        .. note::

            If you want to bypass :exc:`.UserInputError` derived exceptions,
            it is recommended to use the regular :meth:`~.Context.invoke`
            as it will work more naturally. After all, this will end up
            using the old arguments the user has used and will thus just
            fail again.

        Parameters
        ------------
        call_hooks: :class:`bool`
            Whether to call the before and after invoke hooks.
        restart: :class:`bool`
            Whether to start the call chain from the very beginning
            or where we left off (i.e. the command that caused the error).
            The default is to start where we left off.

        Raises
        -------
        ValueError
            The context to reinvoke is not valid.
        """
        cmd = self.command
        view = self.view
        if cmd is None:
            raise ValueError('This context is not valid.')

        # some state to revert to when we're done
        index, previous = view.index, view.previous
        invoked_with = self.invoked_with
        invoked_subcommand = self.invoked_subcommand
        invoked_parents = self.invoked_parents
        subcommand_passed = self.subcommand_passed

        if restart:
            to_call = cmd.root_parent or cmd
            view.index = len(self.prefix)
            view.previous = 0
            self.invoked_parents = []
            self.invoked_with = view.get_word() # advance to get the root command
        else:
            to_call = cmd

        try:
            await to_call.reinvoke(self, call_hooks=call_hooks)
        finally:
            self.command = cmd
            view.index = index
            view.previous = previous
            self.invoked_with = invoked_with
            self.invoked_subcommand = invoked_subcommand
            self.invoked_parents = invoked_parents
            self.subcommand_passed = subcommand_passed

    @property
    def valid(self):
        """:class:`bool`: Checks if the invocation context is valid to be invoked with."""
        return self.prefix is not None and self.command is not None

    async def _get_channel(self):
        return self.channel

    @property
    def cog(self):
        """Optional[:class:`.Cog`]: Returns the cog associated with this context's command. None if it does not exist."""

        if self.command is None:
            return None
        return self.command.cog

    @selfcord.utils.cached_property
    def guild(self):
        """Optional[:class:`.Guild`]: Returns the guild associated with this context's command. None if not available."""
        return self.message.guild

    @selfcord.utils.cached_property
    def channel(self):
        """Union[:class:`.abc.Messageable`]: Returns the channel associated with this context's command.
        Shorthand for :attr:`.Message.channel`.
        """
        return self.message.channel

    @selfcord.utils.cached_property
    def author(self):
        """Union[:class:`~selfcord.User`, :class:`.Member`]:
        Returns the author associated with this context's command. Shorthand for :attr:`.Message.author`
        """
        return self.message.author

    @selfcord.utils.cached_property
    def me(self):
        """Union[:class:`.Member`, :class:`.ClientUser`]:
        Similar to :attr:`.Guild.me` except it may return the :class:`.ClientUser` in private message contexts.
        """
        return self.guild.me if self.guild is not None else self.bot.user

    @property
    def voice_client(self):
        r"""Optional[:class:`.VoiceProtocol`]: A shortcut to :attr:`.Guild.voice_client`\, if applicable."""
        g = self.guild
        return g.voice_client if g else None

    async def send_help(self, *args):
        """send_help(entity=<bot>)

        |coro|

        Shows the help command for the specified entity if given.
        The entity can be a command or a cog.

        If no entity is given, then it'll show help for the
        entire bot.

        If the entity is a string, then it looks up whether it's a
        :class:`Cog` or a :class:`Command`.

        .. note::

            Due to the way this function works, instead of returning
            something similar to :meth:`~.commands.HelpCommand.command_not_found`
            this returns :class:`None` on bad input or no help command.

        Parameters
        ------------
        entity: Optional[Union[:class:`Command`, :class:`Cog`, :class:`str`]]
            The entity to show help for.

        Returns
        --------
        Any
            The result of the help command, if any.
        """
        from .core import Group, Command, wrap_callback
        from .errors import CommandError

        bot = self.bot
        cmd = bot.help_command

        if cmd is None:
            return None

        cmd = cmd.copy()
        cmd.context = self
        if len(args) == 0:
            await cmd.prepare_help_command(self, None)
            mapping = cmd.get_bot_mapping()
            injected = wrap_callback(cmd.send_bot_help)
            try:
                return await injected(mapping)
            except CommandError as e:
                await cmd.on_help_command_error(self, e)
                return None

        entity = args[0]
        if entity is None:
            return None

        if isinstance(entity, str):
            entity = bot.get_cog(entity) or bot.get_command(entity)

        try:
            entity.qualified_name
        except AttributeError:
            # if we're here then it's not a cog, group, or command.
            return None

        await cmd.prepare_help_command(self, entity.qualified_name)

        try:
            if hasattr(entity, '__cog_commands__'):
                injected = wrap_callback(cmd.send_cog_help)
                return await injected(entity)
            elif isinstance(entity, Group):
                injected = wrap_callback(cmd.send_group_help)
                return await injected(entity)
            elif isinstance(entity, Command):
                injected = wrap_callback(cmd.send_command_help)
                return await injected(entity)
            else:
                return None
        except CommandError as e:
            await cmd.on_help_command_error(self, e)

    @selfcord.utils.copy_doc(selfcord.Message.reply)
    async def reply(self, content=None, **kwargs):
        return await self.message.reply(content, **kwargs)
