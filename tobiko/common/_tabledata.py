# Copyright 2025 Red Hat
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
from __future__ import absolute_import

import collections
import csv
import io
import re
import typing

from oslo_log import log


LOG = log.getLogger(__name__)

TableDataType = typing.Iterable[typing.Union[typing.Dict[str, typing.Any],
                                             tuple]]
OptionalTableDataType = typing.Optional[TableDataType]
TableSetItemValueType = typing.Union[typing.Dict[str, typing.Any],
                                     TableDataType]


class TableData(collections.UserList):
    """
    A list-like class for managing tabular data where each item is a dictionary
    and all dictionaries are guaranteed to have the same set of keys (schema).

    This class enforces the schema upon initialization and when new items are
    added. It provides pandas-like functionality for data manipulation.
    """
    _schema: typing.List[str] = []  # Stores the ordered list of expected keys
    data: typing.List[typing.Dict[str, typing.Any]] = []

    def __init__(self,
                 initial_data: OptionalTableDataType = None,
                 columns: typing.List[str] = None):
        """
        Initializes the TableData object.

        Args:
            initial_data: An optional iterable of dictionaries to pre-populate
                          the table.
                          If provided, the schema will be inferred from the
                          first dictionary (if any), and all subsequent
                          dictionaries must conform to this schema.
                          Optionally, a list of tuples can be provided instead
                          of a list of dictionaries.
        """
        super().__init__()
        self._schema = []  # No schema unless initial_data is provided

        if initial_data:
            # Convert to list to iterate multiple times if needed
            initial_data_list = list(initial_data)

            if columns:
                self._schema = columns
                for item in initial_data_list:
                    if not isinstance(item, tuple):
                        raise ValueError("If columns are provided, all items "
                                         "must be tuples")
                    new_item = dict(zip(columns, item))
                    self._validate_item(new_item)
                    self.data.append(new_item)
            else:
                for i, item in enumerate(initial_data_list):
                    if not isinstance(item, dict):
                        raise ValueError("If columns are not provided, all "
                                         "items must be dictionaries")
                    if i == 0:
                        # Infer schema from the first item's keys
                        # (order matters)
                        self._schema = list(item.keys())
                    else:
                        self._validate_item(item)
                    self.data.append(item)  # Add to the internal list

    @classmethod
    def from_dict(cls, data_dict: typing.Dict[str, typing.List[typing.Any]]):
        """
        Create a TableData object from a dictionary of lists (pandas-style).

        Args:
            data_dict: Dictionary where keys are column names and values are
                      lists of values for that column.

        Returns:
            TableData object
        """
        if not data_dict:
            return cls()

        # Get all keys (column names)
        columns = list(data_dict.keys())

        # Check that all lists have the same length
        lengths = [len(data_dict[col]) for col in columns]
        if not all(length == lengths[0] for length in lengths):
            raise ValueError("All columns must have the same number of rows")

        # Convert to list of dictionaries
        num_rows = lengths[0] if lengths else 0
        rows = []
        for i in range(num_rows):
            row = {col: data_dict[col][i] for col in columns}
            rows.append(row)

        return cls(rows)

    @classmethod
    def read_csv(cls, stream_or_string, header=None, skiprows=0,
                 columns=None, sep=',', delim_whitespace=False):
        """
        Read CSV data into a TableData object.

        Args:
            stream_or_string: String, StringIO, or file-like object
            header: Row number to use as column names, None means no header
            skiprows: Number of rows to skip at the beginning
            columns: List of column names to use
            sep: Delimiter to use
            delim_whitespace: Use whitespace as delimiter

        Returns:
            TableData object
        """
        stream = cls._prepare_stream(stream_or_string)
        lines = cls._read_csv_lines(stream, skiprows, sep, delim_whitespace)

        if not lines:
            return cls()

        column_names = cls._determine_column_names(lines, header, columns)
        rows = cls._convert_lines_to_rows(lines, column_names, header)

        return cls(rows)

    @classmethod
    def _prepare_stream(cls, stream_or_string):
        """Prepare input stream for reading."""
        if isinstance(stream_or_string, str):
            return io.StringIO(stream_or_string)
        return stream_or_string

    @classmethod
    def _read_csv_lines(cls, stream, skiprows, sep, delim_whitespace):
        """Read and parse CSV lines from stream."""
        # Skip initial rows
        for _ in range(skiprows):
            try:
                next(stream)
            except StopIteration:
                break

        # Handle delim_whitespace
        if delim_whitespace:
            return cls._read_whitespace_delimited(stream)
        elif len(sep) > 1:
            # Handle multi-character delimiters
            return cls._read_multi_char_delimited(stream, sep)
        else:
            reader = csv.reader(stream, delimiter=sep)
            return list(reader)

    @classmethod
    def _read_whitespace_delimited(cls, stream):
        """Read whitespace-delimited data."""
        lines = []
        for line in stream:
            line = line.strip()
            if line:
                # Split on any whitespace and filter empty strings
                parts = [part for part in line.split() if part]
                lines.append(parts)
        return lines

    @classmethod
    def _read_multi_char_delimited(cls, stream, sep):
        """Read data with multi-character delimiter."""
        lines = []
        for line in stream:
            line = line.rstrip('\n\r')  # Remove only line endings
            if line:
                parts = line.split(sep)
                lines.append(parts)
        return lines

    @classmethod
    def _determine_column_names(cls, lines, header, columns):
        """Determine column names from header, columns, or generate defaults.
        """
        if header is not None and header < len(lines):
            return lines[header]
        elif columns:
            return columns
        else:
            # Generate default column names
            num_cols = len(lines[0]) if lines else 0
            return [str(i) for i in range(num_cols)]

    @classmethod
    def _convert_lines_to_rows(cls, lines, column_names, header):
        """Convert parsed lines to list of dictionaries."""
        # Determine which lines contain data
        if header is not None and header < len(lines):
            data_lines = lines[header + 1:]
        else:
            data_lines = lines

        # Convert to dictionaries
        rows = []
        for line in data_lines:
            if len(line) >= len(column_names):
                row = {col: val for col, val in zip(column_names, line)}
                rows.append(row)

        return rows

    @property
    def schema(self) -> typing.List[str]:
        """Returns the ordered list of keys (headers) for the table."""
        return self._schema

    @property
    def columns(self) -> typing.List[str]:
        """Alias for schema to match pandas API."""
        return self._schema

    @columns.setter
    def columns(self, new_columns: typing.List[str]):
        """Set column names (pandas-style)."""
        if len(new_columns) != len(self._schema):
            raise ValueError(
                "Number of new columns must match existing schema")

        # Update all rows with new column names
        new_data = []
        for row in self.data:
            new_row = {new_col: row[old_col]
                       for new_col, old_col in zip(new_columns, self._schema)}
            new_data.append(new_row)

        self._schema = list(new_columns)
        self.data = new_data

    @property
    def empty(self) -> bool:
        """Check if table is empty (pandas-style)."""
        return len(self.data) == 0

    def _validate_item(self, item: typing.Union[typing.Dict[str, typing.Any],
                                                tuple]):
        """
        Internal method to validate if a dictionary conforms to the current
        schema.
        Raises ValueError if the item does not conform.
        """
        if not isinstance(item, dict):
            raise TypeError(
                f"Items must be dictionaries, but got {type(item)}")

        if not self._schema:
            # If schema is not yet set, infer it from the first item
            self._schema = list(item.keys())
            if not self._schema:  # Handle empty dictionary as first item
                raise ValueError("Cannot infer schema from an empty "
                                 "dictionary as the first item.")
        else:
            # Check if the keys match the schema
            if set(item.keys()) != set(self._schema):
                raise ValueError("Dictionary keys do not match schema. "
                                 f"Expected {set(self._schema)}, "
                                 f"got {set(item.keys())}")

    def append(self, item: typing.Union[typing.Dict[str, typing.Any], tuple]):
        """Appends a dictionary to the table, enforcing schema."""
        self._validate_item(item)
        super().append(item)

    def insert(self, i: int, item: typing.Dict[str, typing.Any]):
        """Inserts a dictionary into the table, enforcing schema."""
        self._validate_item(item)
        super().insert(i, item)

    # The correct signature for __setitem__ to avoid MyPy errors
    @typing.overload
    def __setitem__(self,
                    key: typing.SupportsIndex,
                    value: typing.Dict[str, typing.Any]): ...

    @typing.overload
    def __setitem__(self,
                    key: slice,
                    value: TableDataType): ...

    def __setitem__(self,
                    key: typing.Union[typing.SupportsIndex, slice],
                    value: TableSetItemValueType):
        """Sets an item or slice, enforcing schema."""
        if isinstance(key, slice):
            if not isinstance(value, list):
                raise TypeError(
                    "Must assign a list of dictionaries to a slice")
            for item in value:
                self._validate_item(item)
        else:
            if not isinstance(value, dict):
                raise TypeError(
                    "Must assign a dictionaries to an index")
            self._validate_item(value)
        super().__setitem__(key, value)

    # You might also want to override __add__ and __iadd__ for concatenation
    def __add__(self, other: TableDataType):
        if not isinstance(other, list):
            other = list(other)
        new_data = self.data + other
        return type(self)(new_data)  # Create a new re-validated instance

    def __iadd__(self, other: TableDataType):
        for item in other:
            self.append(item)  # Use append to ensure validation
        return self

    def query(self, expr: str) -> 'TableData':
        """
        Query the table using a simple expression (pandas-style).

        Supports expressions like:
        - column_name == "value"
        - column_name != "value"
        - column_name.str.contains("substring")

        Args:
            expr: Query expression string

        Returns:
            New TableData with filtered results
        """
        results = []
        LOG.debug('filtering data with expression: %s' % expr)

        for row in self.data:
            # Simple expression evaluation
            # Replace column names with their values for evaluation
            eval_expr = expr

            # Handle string contains operations
            contains_match = re.search(r'(\w+)\.str\.contains\("([^"]+)"\)',
                                       expr)
            if contains_match:
                col_name, search_str = contains_match.groups()
                if col_name in row:
                    val = str(row[col_name])
                    if search_str in val:
                        results.append(row)
                continue

            # Handle equality/inequality operations
            # Sort schema by length (descending) to replace longer names first
            # This prevents substring matches (e.g., 'resource' vs others)
            for col_name in sorted(self._schema, key=len, reverse=True):
                # Use word boundary regex to match only complete column names
                pattern = r'\b' + re.escape(col_name) + r'\b'
                if re.search(pattern, eval_expr):
                    # Replace column name with quoted value for safe eval
                    col_value = row[col_name]
                    if isinstance(col_value, str):
                        # Use lambda to avoid escape sequence interpretation
                        # Bind col_value to avoid cell-var-from-loop warning
                        eval_expr = re.sub(
                            pattern,
                            typing.cast(typing.Callable[[typing.Any], str],
                                        lambda m, val=col_value: f'"{val}"'),
                            eval_expr)
                    else:
                        # Use lambda to avoid escape sequence interpretation
                        # Bind col_value to avoid cell-var-from-loop warning
                        eval_expr = re.sub(
                            pattern,
                            typing.cast(typing.Callable[[typing.Any], str],
                                        lambda m, val=col_value: str(val)),
                            eval_expr)

            LOG.debug('final expression to evaluate: %s' % eval_expr)
            try:
                # Use eval with restricted namespace to support comparisons
                # while maintaining safety by preventing access to builtins
                if eval( # noqa; pylint: disable=eval-used
                        eval_expr, {"__builtins__": {}}, {}):
                    results.append(row)
            except (SyntaxError, NameError, ValueError):
                # If expression can't be evaluated, skip this row
                continue

        return TableData(results)

    def __getitem__(self, key):
        """
        Support pandas-style column access and boolean indexing.
        """
        if isinstance(key, str):
            # Column access - return a ColumnData object
            return ColumnData([row[key] for row in self.data], key)
        elif isinstance(key, list) and all(isinstance(k, bool) for k in key):
            # Boolean indexing
            if len(key) != len(self.data):
                raise ValueError(
                    "Boolean index length doesn't match table length")
            results = [row for row, include in zip(self.data, key) if include]
            return TableData(results)
        else:
            # Regular list indexing
            return super().__getitem__(key)

    def replace(self, to_replace=None, value=None, regex=False, inplace=False):
        """
        Replace values in the table (pandas-style).

        Args:
            to_replace: Value or dict of values to replace
            value: Value to replace with
            regex: Whether to_replace is a regex pattern
            inplace: Whether to modify this object or return a new one
        """
        target = self if inplace else TableData(self.data)

        for i, row in enumerate(target.data):
            new_row = {}
            for col, val in row.items():
                new_val = val

                if isinstance(to_replace, dict):
                    if col in to_replace:
                        pattern = to_replace[col]
                        if regex:
                            new_val = re.sub(pattern, value or '', str(val))
                        else:
                            if val == pattern:
                                new_val = value
                elif to_replace is not None:
                    if regex:
                        new_val = re.sub(to_replace, value or '', str(val))
                    else:
                        if val == to_replace:
                            new_val = value

                new_row[col] = new_val

            target.data[i] = new_row

        if not inplace:
            return target

    def to_csv(self, path_or_buf=None):
        """
        Write table to CSV format (pandas-style).

        Args:
            path_or_buf: File path or buffer to write to
        """
        output = io.StringIO()

        if self._schema and self.data:
            writer = csv.DictWriter(output, fieldnames=self._schema)
            writer.writeheader()
            writer.writerows(self.data)

        csv_string = output.getvalue()

        if path_or_buf is None:
            return csv_string
        elif hasattr(path_or_buf, 'write'):
            path_or_buf.write(csv_string)
        else:
            with open(path_or_buf, 'w', newline='') as f:
                f.write(csv_string)

    def to_string(self):
        """
        Return string representation of table (pandas-style).
        """
        if not self.data:
            return "Empty TableData"

        # Calculate column widths
        col_widths = {}
        for col in self._schema:
            col_widths[col] = len(col)
            for row in self.data:
                col_widths[col] = max(col_widths[col], len(str(row[col])))

        # Build string representation
        lines = []

        # Header
        header_parts = []
        for col in self._schema:
            header_parts.append(col.ljust(col_widths[col]))
        lines.append('  '.join(header_parts))

        # Data rows
        for row in self.data:
            row_parts = []
            for col in self._schema:
                row_parts.append(str(row[col]).ljust(col_widths[col]))
            lines.append('  '.join(row_parts))

        return '\n'.join(lines)

    def concat(self, others: typing.List['TableData']):
        """
        Concatenate multiple TableData objects (pandas-style).

        Args:
            others: List of other TableData objects to concatenate
        Returns:
            New TableData object with concatenated data
        """
        all_data = list(self.data)
        for other in others:
            all_data.extend(other.data)
        return TableData(all_data)

    def __str__(self):
        return self.to_string()

    def __repr__(self):
        return f"{type(self).__name__}({self.data!r})"


class ColumnData:
    """
    Represents a column of data with pandas-like functionality.
    """

    def __init__(self, data: typing.List[typing.Any], name=None):
        self.data = data
        self.name = name

    @property
    def values(self):
        """Return values as a list-like object with item() method."""
        return ColumnValues(self.data)

    def unique(self):
        """Return unique values."""
        seen = set()
        unique_vals = []
        for val in self.data:
            if val not in seen:
                seen.add(val)
                unique_vals.append(val)
        return unique_vals

    def tolist(self):
        """Convert to list."""
        return list(self.data)

    def count(self):
        """Count non-null values."""
        return len([val for val in self.data if val is not None])

    @property
    def str(self):
        """String operations."""
        return ColumnStrOperations(self.data)


class ColumnValues:
    """
    Wrapper for column values that provides item() method.
    """

    def __init__(self, data: typing.List[typing.Any]):
        self.data = data

    def item(self):
        """Return single value (like pandas Series.values.item())."""
        if len(self.data) == 1:
            return self.data[0]
        elif len(self.data) == 0:
            raise ValueError("Can't call item() on empty data")
        else:
            raise ValueError("Can only call item() on single-element data")


class ColumnStrOperations:
    """
    String operations on column data.
    """

    def __init__(self, data: typing.List[typing.Any]):
        self.data = data

    def contains(self, pattern: str):
        """Check if string contains pattern."""
        return [pattern in str(val) for val in self.data]


# Static function for concatenating TableData objects (pandas-style)
def concat(tables: typing.List[TableData]) -> TableData:
    """
    Concatenate multiple TableData objects.

    Args:
        tables: List of TableData objects to concatenate
    Returns:
        New TableData object with concatenated data
    """
    if not tables:
        return TableData()

    all_data = []
    for table in tables:
        all_data.extend(table.data)

    return TableData(all_data)
