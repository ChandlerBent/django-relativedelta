import re

from django.db import models
from django.utils.translation import ugettext_lazy as _

from dateutils import relativedelta

# This is not quite ISO8601, as it allows the SQL/Postgres extension
# of allowing a minus sign in the values, and you can mix weeks with
# other units (which ISO doesn't allow).
iso8601_duration_re = re.compile(
    r'P'
    r'(?:(?P<years>-?\d+(?:\.\d+)?)Y)?'
    r'(?:(?P<months>-?\d+(?:\.\d+)?)M)?'
    r'(?:(?P<weeks>-?\d+(?:\.\d+)?)W)?'
    r'(?:(?P<days>-?\d+(?:\.\d+)?)D)?'
    r'(?:T'
    r'(?:(?P<hours>-?\d+(?:\.\d+)?)H)?'
    r'(?:(?P<minutes>-?\d+(?:\.\d+)?)M)?'
    r'(?:(?P<seconds>-?\d+(?:\.\d+)?)S)?'
    r')?'
    r'$'
)

# Parse ISO8601 timespec
def parse_relativedelta(str):
	m = iso8601_duration_re.match(str)
	try:
		args = {k: float(v) if v else 0 for k, v in m.groupdict().items()}
		return relativedelta(**args) if m else None
	except ValueError:
		return None


# Format ISO8601 timespec
def format_relativedelta(relativedelta):
	result_big = ''
	# TODO: We could always include all components, but that's kind of
	# ugly, since one second would be formatted as 'P0Y0M0W0DT0M1S'
	if relativedelta.years:
		result_big += '{}Y'.format(relativedelta.years)
	if relativedelta.months:
		result_big += '{}M'.format(relativedelta.months)
	if relativedelta.weeks:
		result_big += '{}W'.format(relativedelta.weeks)
	if relativedelta.days:
		result_big += '{}D'.format(relativedelta.days)

	result_small = ''
	if relativedelta.hours:
		result_small += '{}H'.format(relativedelta.hours)
	if relativedelta.minutes:
		result_small += '{}M'.format(relativedelta.minutes)
	# Microseconds is allowed here as a convenience, the user may have
	# used normalized(), which can result in microseconds
	if relativedelta.seconds:
		seconds = relativedelta.seconds
		if relativedelta.microseconds:
			seconds += relativedelta.microseconds / 1000.0
		result_small += '{}S'.format(seconds)

	if len(result_small) > 0:
		return 'P{}T{}'.format(result_big, result_small)
	else:
		return 'P{}'.format(result_big)



class RelativeDeltaField(models.Field):
	"""Stores dateutil.relativedelta objects.

	Uses INTERVAL on PostgreSQL.
	"""
	empty_strings_allowed = False
	default_error_messages = {
		'invalid': _("'%(value)s' value has an invalid format. It must be in "
					 "ISO8601 interval format.")
	}
	description = _("RelativeDelta")


	def db_type(self, connection):
		if connection.settings_dict['ENGINE'] == 'django.db.backends.postgresql_psycopg2':
			return 'interval'
		else:
			raise ValueError(_('RelativeDeltaField only supports PostgreSQL for storage'))


	def to_python(self, value):
		if value is None or isinstance(value, relativedelta):
			return value
		elif isinstance(value, datetime.timedelta):
			return relativedelta() + value

		try:
			return parse_relativedelta(value)
		except ValueError:
			raise exceptions.ValidationError(
				self.error_messages['invalid'],
				code='invalid',
				params={'value': value},
			)


	def get_db_prep_value(self, value, connection, prepared=False):
		if value is None:
			return value
		else:
			return format_relativedelta(value)


	# This is a bit of a mindfuck.  We have to cast the output field
	# as text to bypass the standard deserialisation of PsycoPg2 to
	# datetime.timedelta, which loses information.  We then parse it
	# ourselves in convert_relativedeltafield_value().
	#
	# We make it easier for ourselves by doing some formatting here,
	# so that we don't need to rely on weird detection logic for the
	# current value of IntervalStyle (PsycoPg2 actually gets this
	# wrong; it only checks / sets DateStyle, but not IntervalStyle)
	#
	# We can't simply replace or remove PsycoPg2's parser, because
	# that would mess with any existing Django DurationFields, since
	# Django assumes PsycoPg2 returns pre-parsed datetime.timedeltas.
	def select_format(self, compiler, sql, params):
		fmt = 'to_char(%s, \'PYYYY"Y"MM"M"DD"DT"HH"H"MI"M"SS.US"S"\')' % sql
		return fmt, params


	def get_db_converters(self, connection):
		return [self.convert_relativedeltafield_value]


	def convert_relativedeltafield_value(self, value, expression, connection, context):
		if value is not None:
			return parse_relativedelta(value)


	def value_to_string(self, obj):
		val = self.value_from_object(obj)
		return '' if val is None else format_relativedelta(val)