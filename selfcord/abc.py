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

import abc
import sys
import copy
import asyncio

from .iterators import HistoryIterator
from .context_managers import Typing
from .enums import ChannelType
from .errors import InvalidArgument, ClientException
from .mentions import AllowedMentions
from .permissions import PermissionOverwrite, Permissions
from .role import Role
from .invite import Invite
from .file import File
from .voice_client import VoiceClient, VoiceProtocol
from . import utils

class _Undefined:
    def __repr__(self):
        return 'see-below'

_undefined = _Undefined()

class Snowflake(metaclass=abc.ABCMeta):
    """An ABC that details the common operations on a Discord model.

    Almost all :ref:`Discord models <discord_api_models>` meet this
    abstract base class.

    If you want to create a snowflake on your own, consider using
    :class:`.Object`.

    Attributes
    -----------
    id: :class:`int`
        The model's unique ID.
    """
    __slots__ = ()

    @property
    @abc.abstractmethod
    def created_at(self):
        """:class:`datetime.datetime`: Returns the model's creation time as a naive datetime in UTC."""
        raise NotImplementedError

    @classmethod
    def __subclasshook__(cls, C):
        if cls is Snowflake:
            mro = C.__mro__
            for attr in ('created_at', 'id'):
                for base in mro:
                    if attr in base.__dict__:
                        break
                else:
                    return NotImplemented
            return True
        return NotImplemented

class User(metaclass=abc.ABCMeta):
    """An ABC that details the common operations on a Discord user.

    The following implement this ABC:

    - :class:`~selfcord.User`
    - :class:`~selfcord.ClientUser`
    - :class:`~selfcord.Member`

    This ABC must also implement :class:`~selfcord.abc.Snowflake`.

    Attributes
    -----------
    name: :class:`str`
        The user's username.
    discriminator: :class:`str`
        The user's discriminator.
    avatar: Optional[:class:`str`]
        The avatar hash the user has.
    bot: :class:`bool`
        If the user is a bot account.
    """
    __slots__ = ()

    @property
    @abc.abstractmethod
    def display_name(self):
        """:class:`str`: Returns the user's display name."""
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def mention(self):
        """:class:`str`: Returns a string that allows you to mention the given user."""
        raise NotImplementedError

    @classmethod
    def __subclasshook__(cls, C):
        if cls is User:
            if Snowflake.__subclasshook__(C) is NotImplemented:
                return NotImplemented

            mro = C.__mro__
            for attr in ('display_name', 'mention', 'name', 'avatar', 'discriminator', 'bot'):
                for base in mro:
                    if attr in base.__dict__:
                        break
                else:
                    return NotImplemented
            return True
        return NotImplemented

class PrivateChannel(metaclass=abc.ABCMeta):
    """An ABC that details the common operations on a private Discord channel.

    The following implement this ABC:

    - :class:`~selfcord.DMChannel`
    - :class:`~selfcord.GroupChannel`

    This ABC must also implement :class:`~selfcord.abc.Snowflake`.

    Attributes
    -----------
    me: :class:`~selfcord.ClientUser`
        The user presenting yourself.
    """
    __slots__ = ()

    @classmethod
    def __subclasshook__(cls, C):
        if cls is PrivateChannel:
            if Snowflake.__subclasshook__(C) is NotImplemented:
                return NotImplemented

            mro = C.__mro__
            for base in mro:
                if 'me' in base.__dict__:
                    return True
            return NotImplemented
        return NotImplemented

class _Overwrites:
    __slots__ = ('id', 'allow', 'deny', 'type')

    def __init__(self, **kwargs):
        self.id = kwargs.pop('id')
        self.allow = int(kwargs.pop('allow_new', 0))
        self.deny = int(kwargs.pop('deny_new', 0))
        
        # 'type' 값을 str로 변환 후 sys.intern으로 처리
        self.type = sys.intern(str(kwargs.pop('type')))  # str()로 변환 후 sys.intern

    def _asdict(self):
        return {
            'id': self.id,
            'allow': str(self.allow),
            'deny': str(self.deny),
            'type': self.type,
        }

class GuildChannel:
    """An ABC that details the common operations on a Discord guild channel.

    The following implement this ABC:

    - :class:`~selfcord.TextChannel`
    - :class:`~selfcord.VoiceChannel`
    - :class:`~selfcord.CategoryChannel`
    - :class:`~selfcord.StageChannel`

    This ABC must also implement :class:`~selfcord.abc.Snowflake`.

    Attributes
    -----------
    name: :class:`str`
        The channel name.
    guild: :class:`~selfcord.Guild`
        The guild the channel belongs to.
    position: :class:`int`
        The position in the channel list. This is a number that starts at 0.
        e.g. the top channel is position 0.
    """
    __slots__ = ()

    def __str__(self):
        return self.name

    @property
    def _sorting_bucket(self):
        raise NotImplementedError

    async def _move(self, position, parent_id=None, lock_permissions=False, *, reason):
        if position < 0:
            raise InvalidArgument('Channel position cannot be less than 0.')

        http = self._state.http
        bucket = self._sorting_bucket
        channels = [c for c in self.guild.channels if c._sorting_bucket == bucket]

        channels.sort(key=lambda c: c.position)

        try:
            # remove ourselves from the channel list
            channels.remove(self)
        except ValueError:
            # not there somehow lol
            return
        else:
            index = next((i for i, c in enumerate(channels) if c.position >= position), len(channels))
            # add ourselves at our designated position
            channels.insert(index, self)

        payload = []
        for index, c in enumerate(channels):
            d = {'id': c.id, 'position': index}
            if parent_id is not _undefined and c.id == self.id:
                d.update(parent_id=parent_id, lock_permissions=lock_permissions)
            payload.append(d)

        await http.bulk_channel_update(self.guild.id, payload, reason=reason)
        self.position = position
        if parent_id is not _undefined:
            self.category_id = int(parent_id) if parent_id else None

    async def _edit(self, options, reason):
        try:
            parent = options.pop('category')
        except KeyError:
            parent_id = _undefined
        else:
            parent_id = parent and parent.id

        try:
            options['rate_limit_per_user'] = options.pop('slowmode_delay')
        except KeyError:
            pass

        try:
            rtc_region = options.pop('rtc_region')
        except KeyError:
            pass
        else:
            options['rtc_region'] = None if rtc_region is None else str(rtc_region)

        lock_permissions = options.pop('sync_permissions', False)

        try:
            position = options.pop('position')
        except KeyError:
            if parent_id is not _undefined:
                if lock_permissions:
                    category = self.guild.get_channel(parent_id)
                    options['permission_overwrites'] = [c._asdict() for c in category._overwrites]
                options['parent_id'] = parent_id
            elif lock_permissions and self.category_id is not None:
                # if we're syncing permissions on a pre-existing channel category without changing it
                # we need to update the permissions to point to the pre-existing category
                category = self.guild.get_channel(self.category_id)
                options['permission_overwrites'] = [c._asdict() for c in category._overwrites]
        else:
            await self._move(position, parent_id=parent_id, lock_permissions=lock_permissions, reason=reason)

        overwrites = options.get('overwrites', None)
        if overwrites is not None:
            perms = []
            for target, perm in overwrites.items():
                if not isinstance(perm, PermissionOverwrite):
                    raise InvalidArgument('Expected PermissionOverwrite received {0.__name__}'.format(type(perm)))

                allow, deny = perm.pair()
                payload = {
                    'allow': allow.value,
                    'deny': deny.value,
                    'id': target.id
                }

                if isinstance(target, Role):
                    payload['type'] = 'role'
                else:
                    payload['type'] = 'member'

                perms.append(payload)
            options['permission_overwrites'] = perms

        try:
            ch_type = options['type']
        except KeyError:
            pass
        else:
            if not isinstance(ch_type, ChannelType):
                raise InvalidArgument('type field must be of type ChannelType')
            options['type'] = ch_type.value

        if options:
            data = await self._state.http.edit_channel(self.id, reason=reason, **options)
            self._update(self.guild, data)

    def _fill_overwrites(self, data):
        self._overwrites = []
        everyone_index = 0
        everyone_id = self.guild.id

        for index, overridden in enumerate(data.get('permission_overwrites', [])):
            overridden_id = int(overridden.pop('id'))
            self._overwrites.append(_Overwrites(id=overridden_id, **overridden))

            if overridden['type'] == 'member':
                continue

            if overridden_id == everyone_id:
                # the @everyone role is not guaranteed to be the first one
                # in the list of permission overwrites, however the permission
                # resolution code kind of requires that it is the first one in
                # the list since it is special. So we need the index so we can
                # swap it to be the first one.
                everyone_index = index

        # do the swap
        tmp = self._overwrites
        if tmp:
            tmp[everyone_index], tmp[0] = tmp[0], tmp[everyone_index]

    @property
    def changed_roles(self):
        """List[:class:`~selfcord.Role`]: Returns a list of roles that have been overridden from
        their default values in the :attr:`~selfcord.Guild.roles` attribute."""
        ret = []
        g = self.guild
        for overwrite in filter(lambda o: o.type == 'role', self._overwrites):
            role = g.get_role(overwrite.id)
            if role is None:
                continue

            role = copy.copy(role)
            role.permissions.handle_overwrite(overwrite.allow, overwrite.deny)
            ret.append(role)
        return ret

    @property
    def mention(self):
        """:class:`str`: The string that allows you to mention the channel."""
        return '<#%s>' % self.id

    @property
    def created_at(self):
        """:class:`datetime.datetime`: Returns the channel's creation time in UTC."""
        return utils.snowflake_time(self.id)

    def overwrites_for(self, obj):
        """Returns the channel-specific overwrites for a member or a role.

        Parameters
        -----------
        obj: Union[:class:`~selfcord.Role`, :class:`~selfcord.abc.User`]
            The role or user denoting
            whose overwrite to get.

        Returns
        ---------
        :class:`~selfcord.PermissionOverwrite`
            The permission overwrites for this object.
        """

        if isinstance(obj, User):
            predicate = lambda p: p.type == 'member'
        elif isinstance(obj, Role):
            predicate = lambda p: p.type == 'role'
        else:
            predicate = lambda p: True

        for overwrite in filter(predicate, self._overwrites):
            if overwrite.id == obj.id:
                allow = Permissions(overwrite.allow)
                deny = Permissions(overwrite.deny)
                return PermissionOverwrite.from_pair(allow, deny)

        return PermissionOverwrite()

    @property
    def overwrites(self):
        """Returns all of the channel's overwrites.

        This is returned as a dictionary where the key contains the target which
        can be either a :class:`~selfcord.Role` or a :class:`~selfcord.Member` and the value is the
        overwrite as a :class:`~selfcord.PermissionOverwrite`.

        Returns
        --------
        Mapping[Union[:class:`~selfcord.Role`, :class:`~selfcord.Member`], :class:`~selfcord.PermissionOverwrite`]
            The channel's permission overwrites.
        """
        ret = {}
        for ow in self._overwrites:
            allow = Permissions(ow.allow)
            deny = Permissions(ow.deny)
            overwrite = PermissionOverwrite.from_pair(allow, deny)

            if ow.type == 'role':
                target = self.guild.get_role(ow.id)
            elif ow.type == 'member':
                target = self.guild.get_member(ow.id)

            # TODO: There is potential data loss here in the non-chunked
            # case, i.e. target is None because get_member returned nothing.
            # This can be fixed with a slight breaking change to the return type,
            # i.e. adding selfcord.Object to the list of it
            # However, for now this is an acceptable compromise.
            if target is not None:
                ret[target] = overwrite
        return ret

    @property
    def category(self):
        """Optional[:class:`~selfcord.CategoryChannel`]: The category this channel belongs to.

        If there is no category then this is ``None``.
        """
        return self.guild.get_channel(self.category_id)

    @property
    def permissions_synced(self):
        """:class:`bool`: Whether or not the permissions for this channel are synced with the
        category it belongs to.

        If there is no category then this is ``False``.

        .. versionadded:: 1.3
        """
        category = self.guild.get_channel(self.category_id)
        return bool(category and category.overwrites == self.overwrites)

    def permissions_for(self, member):
        """Handles permission resolution for the current :class:`~selfcord.Member`.

        This function takes into consideration the following cases:

        - Guild owner
        - Guild roles
        - Channel overrides
        - Member overrides

        Parameters
        ----------
        member: :class:`~selfcord.Member`
            The member to resolve permissions for.

        Returns
        -------
        :class:`~selfcord.Permissions`
            The resolved permissions for the member.
        """

        # The current cases can be explained as:
        # Guild owner get all permissions -- no questions asked. Otherwise...
        # The @everyone role gets the first application.
        # After that, the applied roles that the user has in the channel
        # (or otherwise) are then OR'd together.
        # After the role permissions are resolved, the member permissions
        # have to take into effect.
        # After all that is done.. you have to do the following:

        # If manage permissions is True, then all permissions are set to True.

        # The operation first takes into consideration the denied
        # and then the allowed.

        if self.guild.owner_id == member.id:
            return Permissions.all()

        default = self.guild.default_role
        base = Permissions(default.permissions.value)
        roles = member._roles
        get_role = self.guild.get_role

        # Apply guild roles that the member has.
        for role_id in roles:
            role = get_role(role_id)
            if role is not None:
                base.value |= role._permissions

        # Guild-wide Administrator -> True for everything
        # Bypass all channel-specific overrides
        if base.administrator:
            return Permissions.all()

        # Apply @everyone allow/deny first since it's special
        try:
            maybe_everyone = self._overwrites[0]
            if maybe_everyone.id == self.guild.id:
                base.handle_overwrite(allow=maybe_everyone.allow, deny=maybe_everyone.deny)
                remaining_overwrites = self._overwrites[1:]
            else:
                remaining_overwrites = self._overwrites
        except IndexError:
            remaining_overwrites = self._overwrites

        denies = 0
        allows = 0

        # Apply channel specific role permission overwrites
        for overwrite in remaining_overwrites:
            if overwrite.type == 'role' and roles.has(overwrite.id):
                denies |= overwrite.deny
                allows |= overwrite.allow

        base.handle_overwrite(allow=allows, deny=denies)

        # Apply member specific permission overwrites
        for overwrite in remaining_overwrites:
            if overwrite.type == 'member' and overwrite.id == member.id:
                base.handle_overwrite(allow=overwrite.allow, deny=overwrite.deny)
                break

        # if you can't send a message in a channel then you can't have certain
        # permissions as well
        if not base.send_messages:
            base.send_tts_messages = False
            base.mention_everyone = False
            base.embed_links = False
            base.attach_files = False

        # if you can't read a channel then you have no permissions there
        if not base.read_messages:
            denied = Permissions.all_channel()
            base.value &= ~denied.value

        return base

    async def delete(self, *, reason=None):
        """|coro|

        Deletes the channel.

        You must have :attr:`~Permissions.manage_channels` permission to use this.

        Parameters
        -----------
        reason: Optional[:class:`str`]
            The reason for deleting this channel.
            Shows up on the audit log.

        Raises
        -------
        ~selfcord.Forbidden
            You do not have proper permissions to delete the channel.
        ~selfcord.NotFound
            The channel was not found or was already deleted.
        ~selfcord.HTTPException
            Deleting the channel failed.
        """
        await self._state.http.delete_channel(self.id, reason=reason)

    async def set_permissions(self, target, *, overwrite=_undefined, reason=None, **permissions):
        r"""|coro|

        Sets the channel specific permission overwrites for a target in the
        channel.

        The ``target`` parameter should either be a :class:`~selfcord.Member` or a
        :class:`~selfcord.Role` that belongs to guild.

        The ``overwrite`` parameter, if given, must either be ``None`` or
        :class:`~selfcord.PermissionOverwrite`. For convenience, you can pass in
        keyword arguments denoting :class:`~selfcord.Permissions` attributes. If this is
        done, then you cannot mix the keyword arguments with the ``overwrite``
        parameter.

        If the ``overwrite`` parameter is ``None``, then the permission
        overwrites are deleted.

        You must have the :attr:`~Permissions.manage_roles` permission to use this.

        Examples
        ----------

        Setting allow and deny: ::

            await message.channel.set_permissions(message.author, read_messages=True,
                                                                  send_messages=False)

        Deleting overwrites ::

            await channel.set_permissions(member, overwrite=None)

        Using :class:`~selfcord.PermissionOverwrite` ::

            overwrite = selfcord.PermissionOverwrite()
            overwrite.send_messages = False
            overwrite.read_messages = True
            await channel.set_permissions(member, overwrite=overwrite)

        Parameters
        -----------
        target: Union[:class:`~selfcord.Member`, :class:`~selfcord.Role`]
            The member or role to overwrite permissions for.
        overwrite: Optional[:class:`~selfcord.PermissionOverwrite`]
            The permissions to allow and deny to the target, or ``None`` to
            delete the overwrite.
        \*\*permissions
            A keyword argument list of permissions to set for ease of use.
            Cannot be mixed with ``overwrite``.
        reason: Optional[:class:`str`]
            The reason for doing this action. Shows up on the audit log.

        Raises
        -------
        ~selfcord.Forbidden
            You do not have permissions to edit channel specific permissions.
        ~selfcord.HTTPException
            Editing channel specific permissions failed.
        ~selfcord.NotFound
            The role or member being edited is not part of the guild.
        ~selfcord.InvalidArgument
            The overwrite parameter invalid or the target type was not
            :class:`~selfcord.Role` or :class:`~selfcord.Member`.
        """

        http = self._state.http

        if isinstance(target, User):
            perm_type = 'member'
        elif isinstance(target, Role):
            perm_type = 'role'
        else:
            raise InvalidArgument('target parameter must be either Member or Role')

        if isinstance(overwrite, _Undefined):
            if len(permissions) == 0:
                raise InvalidArgument('No overwrite provided.')
            try:
                overwrite = PermissionOverwrite(**permissions)
            except (ValueError, TypeError):
                raise InvalidArgument('Invalid permissions given to keyword arguments.')
        else:
            if len(permissions) > 0:
                raise InvalidArgument('Cannot mix overwrite and keyword arguments.')

        # TODO: wait for event

        if overwrite is None:
            await http.delete_channel_permissions(self.id, target.id, reason=reason)
        elif isinstance(overwrite, PermissionOverwrite):
            (allow, deny) = overwrite.pair()
            await http.edit_channel_permissions(self.id, target.id, allow.value, deny.value, perm_type, reason=reason)
        else:
            raise InvalidArgument('Invalid overwrite type provided.')

    async def _clone_impl(self, base_attrs, *, name=None, reason=None):
        base_attrs['permission_overwrites'] = [
            x._asdict() for x in self._overwrites
        ]
        base_attrs['parent_id'] = self.category_id
        base_attrs['name'] = name or self.name
        guild_id = self.guild.id
        cls = self.__class__
        data = await self._state.http.create_channel(guild_id, self.type.value, reason=reason, **base_attrs)
        obj = cls(state=self._state, guild=self.guild, data=data)

        # temporarily add it to the cache
        self.guild._channels[obj.id] = obj
        return obj

    async def clone(self, *, name=None, reason=None):
        """|coro|

        Clones this channel. This creates a channel with the same properties
        as this channel.

        You must have the :attr:`~selfcord.Permissions.manage_channels` permission to
        do this.

        .. versionadded:: 1.1

        Parameters
        ------------
        name: Optional[:class:`str`]
            The name of the new channel. If not provided, defaults to this
            channel name.
        reason: Optional[:class:`str`]
            The reason for cloning this channel. Shows up on the audit log.

        Raises
        -------
        ~selfcord.Forbidden
            You do not have the proper permissions to create this channel.
        ~selfcord.HTTPException
            Creating the channel failed.

        Returns
        --------
        :class:`.abc.GuildChannel`
            The channel that was created.
        """
        raise NotImplementedError

    async def move(self, **kwargs):
        """|coro|

        A rich interface to help move a channel relative to other channels.

        If exact position movement is required, :meth:`edit` should be used instead.

        You must have the :attr:`~selfcord.Permissions.manage_channels` permission to
        do this.

        .. note::

            Voice channels will always be sorted below text channels.
            This is a Discord limitation.

        .. versionadded:: 1.7

        Parameters
        ------------
        beginning: :class:`bool`
            Whether to move the channel to the beginning of the
            channel list (or category if given).
            This is mutually exclusive with ``end``, ``before``, and ``after``.
        end: :class:`bool`
            Whether to move the channel to the end of the
            channel list (or category if given).
            This is mutually exclusive with ``beginning``, ``before``, and ``after``.
        before: :class:`~selfcord.abc.Snowflake`
            The channel that should be before our current channel.
            This is mutually exclusive with ``beginning``, ``end``, and ``after``.
        after: :class:`~selfcord.abc.Snowflake`
            The channel that should be after our current channel.
            This is mutually exclusive with ``beginning``, ``end``, and ``before``.
        offset: :class:`int`
            The number of channels to offset the move by. For example,
            an offset of ``2`` with ``beginning=True`` would move
            it 2 after the beginning. A positive number moves it below
            while a negative number moves it above. Note that this
            number is relative and computed after the ``beginning``,
            ``end``, ``before``, and ``after`` parameters.
        category: Optional[:class:`~selfcord.abc.Snowflake`]
            The category to move this channel under.
            If ``None`` is given then it moves it out of the category.
            This parameter is ignored if moving a category channel.
        sync_permissions: :class:`bool`
            Whether to sync the permissions with the category (if given).
        reason: :class:`str`
            The reason for the move.

        Raises
        -------
        InvalidArgument
            An invalid position was given or a bad mix of arguments were passed.
        Forbidden
            You do not have permissions to move the channel.
        HTTPException
            Moving the channel failed.
        """

        if not kwargs:
            return

        beginning, end = kwargs.get('beginning'), kwargs.get('end')
        before, after = kwargs.get('before'), kwargs.get('after')
        offset = kwargs.get('offset', 0)
        if sum(bool(a) for a in (beginning, end, before, after)) > 1:
            raise InvalidArgument('Only one of [before, after, end, beginning] can be used.')

        bucket = self._sorting_bucket
        parent_id = kwargs.get('category', ...)
        if parent_id not in (..., None):
            parent_id = parent_id.id
            channels = [
                ch
                for ch in self.guild.channels
                if ch._sorting_bucket == bucket
                and ch.category_id == parent_id
            ]
        else:
            channels = [
                ch
                for ch in self.guild.channels
                if ch._sorting_bucket == bucket
                and ch.category_id == self.category_id
            ]

        channels.sort(key=lambda c: (c.position, c.id))

        try:
            # Try to remove ourselves from the channel list
            channels.remove(self)
        except ValueError:
            # If we're not there then it's probably due to not being in the category
            pass

        index = None
        if beginning:
            index = 0
        elif end:
            index = len(channels)
        elif before:
            index = next((i for i, c in enumerate(channels) if c.id == before.id), None)
        elif after:
            index = next((i + 1 for i, c in enumerate(channels) if c.id == after.id), None)

        if index is None:
            raise InvalidArgument('Could not resolve appropriate move position')

        channels.insert(max((index + offset), 0), self)
        payload = []
        lock_permissions = kwargs.get('sync_permissions', False)
        reason = kwargs.get('reason')
        for index, channel in enumerate(channels):
            d = { 'id': channel.id, 'position': index }
            if parent_id is not ... and channel.id == self.id:
                d.update(parent_id=parent_id, lock_permissions=lock_permissions)
            payload.append(d)

        await self._state.http.bulk_channel_update(self.guild.id, payload, reason=reason)


    async def create_invite(self, *, reason=None, **fields):
        """|coro|

        Creates an instant invite from a text or voice channel.

        You must have the :attr:`~Permissions.create_instant_invite` permission to
        do this.

        Parameters
        ------------
        max_age: :class:`int`
            How long the invite should last in seconds. If it's 0 then the invite
            doesn't expire. Defaults to ``0``.
        max_uses: :class:`int`
            How many uses the invite could be used for. If it's 0 then there
            are unlimited uses. Defaults to ``0``.
        temporary: :class:`bool`
            Denotes that the invite grants temporary membership
            (i.e. they get kicked after they disconnect). Defaults to ``False``.
        unique: :class:`bool`
            Indicates if a unique invite URL should be created. Defaults to True.
            If this is set to ``False`` then it will return a previously created
            invite.
        reason: Optional[:class:`str`]
            The reason for creating this invite. Shows up on the audit log.

        Raises
        -------
        ~selfcord.HTTPException
            Invite creation failed.

        ~selfcord.NotFound
            The channel that was passed is a category or an invalid channel.

        Returns
        --------
        :class:`~selfcord.Invite`
            The invite that was created.
        """

        data = await self._state.http.create_invite(self.id, reason=reason, **fields)
        return Invite.from_incomplete(data=data, state=self._state)

    async def invites(self):
        """|coro|

        Returns a list of all active instant invites from this channel.

        You must have :attr:`~Permissions.manage_channels` to get this information.

        Raises
        -------
        ~selfcord.Forbidden
            You do not have proper permissions to get the information.
        ~selfcord.HTTPException
            An error occurred while fetching the information.

        Returns
        -------
        List[:class:`~selfcord.Invite`]
            The list of invites that are currently active.
        """

        state = self._state
        data = await state.http.invites_from_channel(self.id)
        result = []

        for invite in data:
            invite['channel'] = self
            invite['guild'] = self.guild
            result.append(Invite(state=state, data=invite))

        return result

class Messageable(metaclass=abc.ABCMeta):
    """An ABC that details the common operations on a model that can send messages.

    The following implement this ABC:

    - :class:`~selfcord.TextChannel`
    - :class:`~selfcord.DMChannel`
    - :class:`~selfcord.GroupChannel`
    - :class:`~selfcord.User`
    - :class:`~selfcord.Member`
    - :class:`~selfcord.ext.commands.Context`
    """

    __slots__ = ()

    @abc.abstractmethod
    async def _get_channel(self):
        raise NotImplementedError

    async def send(self, content=None, *, tts=False, embed=None, file=None,
                                          files=None, delete_after=None, nonce=None,
                                          allowed_mentions=None, reference=None,
                                          mention_author=None):
        """|coro|

        Sends a message to the destination with the content given.

        The content must be a type that can convert to a string through ``str(content)``.
        If the content is set to ``None`` (the default), then the ``embed`` parameter must
        be provided.

        To upload a single file, the ``file`` parameter should be used with a
        single :class:`~selfcord.File` object. To upload multiple files, the ``files``
        parameter should be used with a :class:`list` of :class:`~selfcord.File` objects.
        **Specifying both parameters will lead to an exception**.

        If the ``embed`` parameter is provided, it must be of type :class:`~selfcord.Embed` and
        it must be a rich embed type.

        Parameters
        ------------
        content: :class:`str`
            The content of the message to send.
        tts: :class:`bool`
            Indicates if the message should be sent using text-to-speech.
        embed: :class:`~selfcord.Embed`
            The rich embed for the content.
        file: :class:`~selfcord.File`
            The file to upload.
        files: List[:class:`~selfcord.File`]
            A list of files to upload. Must be a maximum of 10.
        nonce: :class:`int`
            The nonce to use for sending this message. If the message was successfully sent,
            then the message will have a nonce with this value.
        delete_after: :class:`float`
            If provided, the number of seconds to wait in the background
            before deleting the message we just sent. If the deletion fails,
            then it is silently ignored.
        allowed_mentions: :class:`~selfcord.AllowedMentions`
            Controls the mentions being processed in this message. If this is
            passed, then the object is merged with :attr:`~selfcord.Client.allowed_mentions`.
            The merging behaviour only overrides attributes that have been explicitly passed
            to the object, otherwise it uses the attributes set in :attr:`~selfcord.Client.allowed_mentions`.
            If no object is passed at all then the defaults given by :attr:`~selfcord.Client.allowed_mentions`
            are used instead.

            .. versionadded:: 1.4

        reference: Union[:class:`~selfcord.Message`, :class:`~selfcord.MessageReference`]
            A reference to the :class:`~selfcord.Message` to which you are replying, this can be created using
            :meth:`~selfcord.Message.to_reference` or passed directly as a :class:`~selfcord.Message`. You can control
            whether this mentions the author of the referenced message using the :attr:`~selfcord.AllowedMentions.replied_user`
            attribute of ``allowed_mentions`` or by setting ``mention_author``.

            .. versionadded:: 1.6

        mention_author: Optional[:class:`bool`]
            If set, overrides the :attr:`~selfcord.AllowedMentions.replied_user` attribute of ``allowed_mentions``.

            .. versionadded:: 1.6

        Raises
        --------
        ~selfcord.HTTPException
            Sending the message failed.
        ~selfcord.Forbidden
            You do not have the proper permissions to send the message.
        ~selfcord.InvalidArgument
            The ``files`` list is not of the appropriate size,
            you specified both ``file`` and ``files``,
            or the ``reference`` object is not a :class:`~selfcord.Message`
            or :class:`~selfcord.MessageReference`.

        Returns
        ---------
        :class:`~selfcord.Message`
            The message that was sent.
        """

        channel = await self._get_channel()
        state = self._state
        content = str(content) if content is not None else None
        if embed is not None:
            embed = embed.to_dict()

        if allowed_mentions is not None:
            if state.allowed_mentions is not None:
                allowed_mentions = state.allowed_mentions.merge(allowed_mentions).to_dict()
            else:
                allowed_mentions = allowed_mentions.to_dict()
        else:
            allowed_mentions = state.allowed_mentions and state.allowed_mentions.to_dict()

        if mention_author is not None:
            allowed_mentions = allowed_mentions or AllowedMentions().to_dict()
            allowed_mentions['replied_user'] = bool(mention_author)

        if reference is not None:
            try:
                reference = reference.to_message_reference_dict()
            except AttributeError:
                raise InvalidArgument('reference parameter must be Message or MessageReference') from None

        if file is not None and files is not None:
            raise InvalidArgument('cannot pass both file and files parameter to send()')

        if file is not None:
            if not isinstance(file, File):
                raise InvalidArgument('file parameter must be File')

            try:
                data = await state.http.send_files(channel.id, files=[file], allowed_mentions=allowed_mentions,
                                                   content=content, tts=tts, embed=embed, nonce=nonce,
                                                   message_reference=reference)
            finally:
                file.close()

        elif files is not None:
            if len(files) > 10:
                raise InvalidArgument('files parameter must be a list of up to 10 elements')
            elif not all(isinstance(file, File) for file in files):
                raise InvalidArgument('files parameter must be a list of File')

            try:
                data = await state.http.send_files(channel.id, files=files, content=content, tts=tts,
                                                   embed=embed, nonce=nonce, allowed_mentions=allowed_mentions,
                                                   message_reference=reference)
            finally:
                for f in files:
                    f.close()
        else:
            data = await state.http.send_message(channel.id, content, tts=tts, embed=embed,
                                                                      nonce=nonce, allowed_mentions=allowed_mentions,
                                                                      message_reference=reference)

        ret = state.create_message(channel=channel, data=data)
        if delete_after is not None:
            await ret.delete(delay=delete_after)
        return ret

    async def trigger_typing(self):
        """|coro|

        Triggers a *typing* indicator to the destination.

        *Typing* indicator will go away after 10 seconds, or after a message is sent.
        """

        channel = await self._get_channel()
        await self._state.http.send_typing(channel.id)

    def typing(self):
        """Returns a context manager that allows you to type for an indefinite period of time.

        This is useful for denoting long computations in your bot.

        .. note::

            This is both a regular context manager and an async context manager.
            This means that both ``with`` and ``async with`` work with this.

        Example Usage: ::

            async with channel.typing():
                # do expensive stuff here
                await channel.send('done!')

        """
        return Typing(self)

    async def fetch_message(self, id):
        """|coro|

        Retrieves a single :class:`~selfcord.Message` from the destination.

        This can only be used by bot accounts.

        Parameters
        ------------
        id: :class:`int`
            The message ID to look for.

        Raises
        --------
        ~selfcord.NotFound
            The specified message was not found.
        ~selfcord.Forbidden
            You do not have the permissions required to get a message.
        ~selfcord.HTTPException
            Retrieving the message failed.

        Returns
        --------
        :class:`~selfcord.Message`
            The message asked for.
        """

        channel = await self._get_channel()
        data = await self._state.http.get_message(channel.id, id)
        return self._state.create_message(channel=channel, data=data)

    async def pins(self):
        """|coro|

        Retrieves all messages that are currently pinned in the channel.

        .. note::

            Due to a limitation with the Discord API, the :class:`.Message`
            objects returned by this method do not contain complete
            :attr:`.Message.reactions` data.

        Raises
        -------
        ~selfcord.HTTPException
            Retrieving the pinned messages failed.

        Returns
        --------
        List[:class:`~selfcord.Message`]
            The messages that are currently pinned.
        """

        channel = await self._get_channel()
        state = self._state
        data = await state.http.pins_from(channel.id)
        return [state.create_message(channel=channel, data=m) for m in data]

    def history(self, *, limit=100, before=None, after=None, around=None, oldest_first=None):
        """Returns an :class:`~selfcord.AsyncIterator` that enables receiving the destination's message history.

        You must have :attr:`~Permissions.read_message_history` permissions to use this.

        Examples
        ---------

        Usage ::

            counter = 0
            async for message in channel.history(limit=200):
                if message.author == client.user:
                    counter += 1

        Flattening into a list: ::

            messages = await channel.history(limit=123).flatten()
            # messages is now a list of Message...

        All parameters are optional.

        Parameters
        -----------
        limit: Optional[:class:`int`]
            The number of messages to retrieve.
            If ``None``, retrieves every message in the channel. Note, however,
            that this would make it a slow operation.
        before: Optional[Union[:class:`~selfcord.abc.Snowflake`, :class:`datetime.datetime`]]
            Retrieve messages before this date or message.
            If a date is provided it must be a timezone-naive datetime representing UTC time.
        after: Optional[Union[:class:`~selfcord.abc.Snowflake`, :class:`datetime.datetime`]]
            Retrieve messages after this date or message.
            If a date is provided it must be a timezone-naive datetime representing UTC time.
        around: Optional[Union[:class:`~selfcord.abc.Snowflake`, :class:`datetime.datetime`]]
            Retrieve messages around this date or message.
            If a date is provided it must be a timezone-naive datetime representing UTC time.
            When using this argument, the maximum limit is 101. Note that if the limit is an
            even number then this will return at most limit + 1 messages.
        oldest_first: Optional[:class:`bool`]
            If set to ``True``, return messages in oldest->newest order. Defaults to ``True`` if
            ``after`` is specified, otherwise ``False``.

        Raises
        ------
        ~selfcord.Forbidden
            You do not have permissions to get channel message history.
        ~selfcord.HTTPException
            The request to get message history failed.

        Yields
        -------
        :class:`~selfcord.Message`
            The message with the message data parsed.
        """
        return HistoryIterator(self, limit=limit, before=before, after=after, around=around, oldest_first=oldest_first)

class Connectable(metaclass=abc.ABCMeta):
    """An ABC that details the common operations on a channel that can
    connect to a voice server.

    The following implement this ABC:

    - :class:`~selfcord.VoiceChannel`
    """
    __slots__ = ()

    @abc.abstractmethod
    def _get_voice_client_key(self):
        raise NotImplementedError

    @abc.abstractmethod
    def _get_voice_state_pair(self):
        raise NotImplementedError

    async def connect(self, *, timeout=60.0, reconnect=True, cls=VoiceClient):
        """|coro|

        Connects to voice and creates a :class:`VoiceClient` to establish
        your connection to the voice server.

        Parameters
        -----------
        timeout: :class:`float`
            The timeout in seconds to wait for the voice endpoint.
        reconnect: :class:`bool`
            Whether the bot should automatically attempt
            a reconnect if a part of the handshake fails
            or the gateway goes down.
        cls: Type[:class:`VoiceProtocol`]
            A type that subclasses :class:`~selfcord.VoiceProtocol` to connect with.
            Defaults to :class:`~selfcord.VoiceClient`.

        Raises
        -------
        asyncio.TimeoutError
            Could not connect to the voice channel in time.
        ~selfcord.ClientException
            You are already connected to a voice channel.
        ~selfcord.opus.OpusNotLoaded
            The opus library has not been loaded.

        Returns
        --------
        :class:`~selfcord.VoiceProtocol`
            A voice client that is fully connected to the voice server.
        """

        key_id, _ = self._get_voice_client_key()
        state = self._state

        if state._get_voice_client(key_id):
            raise ClientException('Already connected to a voice channel.')

        client = state._get_client()
        voice = cls(client, self)

        if not isinstance(voice, VoiceProtocol):
            raise TypeError('Type must meet VoiceProtocol abstract base class.')

        state._add_voice_client(key_id, voice)

        try:
            await voice.connect(timeout=timeout, reconnect=reconnect)
        except asyncio.TimeoutError:
            try:
                await voice.disconnect(force=True)
            except Exception:
                # we don't care if disconnect failed because connection failed
                pass
            raise # re-raise

        return voice
