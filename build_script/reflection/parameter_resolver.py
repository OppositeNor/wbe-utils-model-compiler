# Copyright 2025 OppositeNor
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os
import re
from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    pass  # kept for future use

from build_script.reflection.gen_file_info import WBEGenFileInfo


class WBEParameterSource(ABC):
    """Abstract base for parameter value providers used by WBEParameterResolver.

    Implementations supply string values for named parameters referenced as
    ${name} inside generate.json fields.
    """

    @abstractmethod
    def resolve(self, name: str) -> str | None:
        """Resolve a parameter by name.

        Args:
            name: The parameter name to look up.
        Returns:
            The string value, or None if this source does not provide the name.
        """


class WBEDictParameterSource(WBEParameterSource):
    """Parameter source backed by an explicit dict[str, str].

    Args:
        params: Mapping of parameter names to their string values.
    """

    def __init__(self, params: dict[str, str]) -> None:
        self._params = params

    def resolve(self, name: str) -> str | None:
        return self._params.get(name)


class WBEEnvParameterSource(WBEParameterSource):
    """Parameter source backed by environment variables.

    Args:
        prefix: Optional prefix prepended when looking up env vars.
                E.g., prefix="WBE_" means ${foo} looks up os.environ["WBE_foo"].
    """

    def __init__(self, prefix: str = "") -> None:
        self._prefix = prefix

    def resolve(self, name: str) -> str | None:
        return os.environ.get(self._prefix + name)


_PATTERN: re.Pattern[str] = re.compile(r"\$\{([^}]+)\}")


class WBEParameterResolver:
    """Resolves ${name} patterns in strings using an ordered list of sources.

    Sources are queried in declaration order; the first non-None result wins.
    Supports recursive traversal of nested dicts and lists so the entire
    generate.json data tree can be resolved in one call.

    Args:
        sources: Ordered list of WBEParameterSource instances. First match wins.
        strict: If True (default), raise ValueError for any ${name} that no
                source can resolve. If False, unresolved patterns are left as-is.
    """

    def __init__(self, sources: list[WBEParameterSource], strict: bool = True) -> None:
        self._sources = sources
        self._strict = strict

    def with_prepended(self, source: WBEParameterSource) -> "WBEParameterResolver":
        """Return a new resolver with source injected at highest priority.

        Args:
            source: The source to prepend.
        Returns:
            A new WBEParameterResolver whose source list is [source] + self._sources.
        """
        return WBEParameterResolver([source] + self._sources, self._strict)

    def resolve_str(self, text: str) -> str:
        """Replace all ${name} occurrences in text.

        Args:
            text: Input string potentially containing ${name} patterns.
        Returns:
            String with all resolved patterns substituted.
        Raises:
            ValueError: If strict=True and a pattern cannot be resolved by any source.
        """
        def _replace(match: re.Match[str]) -> str:
            name = match.group(1)
            for source in self._sources:
                value = source.resolve(name)
                if value is not None:
                    return value
            if self._strict:
                raise ValueError(
                    f"Unresolved parameter: ${{{name}}}. "
                    f"Declare it in the 'params' field of generate.json or pass it as a build-level source."
                )
            return match.group(0)

        return _PATTERN.sub(_replace, text)

    def resolve_value(self, value: Any) -> Any:
        """Recursively resolve ${name} patterns in value.

        Traverses str, list, and dict values. All other leaf types are
        returned unchanged so that non-string data (integers, booleans,
        metadata objects) pass through without modification.

        Args:
            value: Any value — a plain string, a nested dict, a list, or
                   any other type from the generate.json data tree.
        Returns:
            Value with all string ${name} patterns resolved.
        """
        if isinstance(value, str):
            return self.resolve_str(value)
        if isinstance(value, list):
            return [self.resolve_value(item) for item in value]
        if isinstance(value, dict):
            return {k: self.resolve_value(v) for k, v in value.items()}
        return value

    def resolve_gen_file_info(self, generate_info: WBEGenFileInfo) -> WBEGenFileInfo:
        """Resolve all ${name} patterns in a WBEGenFileInfo entry.

        The entry's own params dict is prepended as the highest-priority source
        before resolution, so per-entry declarations override everything else.
        The returned object is a new instance; the original is not modified.

        Args:
            generate_info: The generation entry to resolve.
        Returns:
            A new WBEGenFileInfo with output_name, template, out_dir, and all
            data string values resolved.
        """
        resolver = self
        if generate_info.params:
            resolver = self.with_prepended(WBEDictParameterSource(generate_info.params))
        return WBEGenFileInfo(
            output_name=resolver.resolve_str(generate_info.output_name),
            template=resolver.resolve_str(generate_info.template),
            out_dir=resolver.resolve_str(generate_info.out_dir),
            params=generate_info.params,
            data={k: resolver.resolve_value(v) for k, v in generate_info.data.items()},
        )
