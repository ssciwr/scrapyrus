from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from saxonche import PySaxonProcessor, PyXdmNode


XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"

_STRIP_NAMESPACES_STYLESHEET = """\
<xsl:stylesheet version="3.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="xml" omit-xml-declaration="yes"/>
  <xsl:mode on-no-match="shallow-copy"/>

  <xsl:template match="*">
    <xsl:element name="{local-name()}">
      <xsl:apply-templates select="@* | node()"/>
    </xsl:element>
  </xsl:template>

  <xsl:template match="@*">
    <xsl:copy/>
  </xsl:template>
</xsl:stylesheet>
"""


def xpath_literal(value: str) -> str:
    """Return *value* as a quoted XPath string literal."""

    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    return "concat(" + ', "\'", '.join(f"'{part}'" for part in value.split("'")) + ")"


def saxon_qname(name: str) -> str:
    """Convert Clark-notation and XML-prefixed names to Saxon EQName syntax."""

    if name.startswith("Q{"):
        return name
    if name.startswith("{"):
        namespace, _, local = name[1:].partition("}")
        return f"Q{{{namespace}}}{local}"
    if name.startswith("xml:"):
        return f"Q{{{XML_NAMESPACE}}}{name.removeprefix('xml:')}"
    return name


def namespace_uri(name: str | None) -> str:
    """Return the namespace URI from a Saxon EQName, or ``""`` if absent."""

    if name is not None and name.startswith("Q{"):
        return name[2:].partition("}")[0]
    return ""


def display_name(name: str | None) -> str:
    """Return a readable local name, preserving the standard ``xml:`` prefix."""

    if name is None:
        return ""
    if name.startswith("Q{"):
        namespace, _, local = name[2:].partition("}")
        return f"xml:{local}" if namespace == XML_NAMESPACE else local
    if name.startswith("{"):
        namespace, _, local = name[1:].partition("}")
        return f"xml:{local}" if namespace == XML_NAMESPACE else local
    return name.rpartition(":")[2]


def parse_xml_document(proc: PySaxonProcessor, path: str | Path) -> PyXdmNode:
    """Parse an XML file and return Saxon's document node."""

    return proc.parse_xml(xml_file_name=str(path))


def parse_xml_text(proc: PySaxonProcessor, xml: str | bytes) -> PyXdmNode:
    """Parse an XML string or UTF-8 encoded XML bytes."""

    if isinstance(xml, bytes):
        xml = xml.decode("utf-8-sig")
    return proc.parse_xml(xml_text=xml)


def document_element(node: PyXdmNode) -> PyXdmNode:
    """Return the document element for a document node, or *node* if it is one."""

    if node.node_kind_str == "element":
        return node
    for child in node.children:
        if child.node_kind_str == "element":
            return child
    raise ValueError("XML document does not contain a document element")


def _matches_name(
    node: PyXdmNode,
    name: str | None,
    local_name: str | None,
) -> bool:
    if node.node_kind_str != "element":
        return False
    if local_name is not None and node.local_name != local_name:
        return False
    if name is None:
        return True
    if name.startswith(("{", "Q{", "xml:")):
        return node.name == saxon_qname(name)
    return node.local_name == name


def direct_children(
    node: PyXdmNode,
    name: str | None = None,
    *,
    local_name: str | None = None,
) -> list[PyXdmNode]:
    """Return direct element children, optionally filtered by element name."""

    return [
        child
        for child in node.children
        if _matches_name(child, name=name, local_name=local_name)
    ]


def first_child(
    node: PyXdmNode,
    name: str | None = None,
    *,
    local_name: str | None = None,
) -> PyXdmNode | None:
    """Return the first matching direct element child."""

    return next(iter(direct_children(node, name, local_name=local_name)), None)


def iter_elements(
    node: PyXdmNode,
    name: str | None = None,
    *,
    local_name: str | None = None,
) -> Iterator[PyXdmNode]:
    """Yield element descendants in document order, including *node* if matched."""

    if _matches_name(node, name=name, local_name=local_name):
        yield node
    for child in node.children:
        if child.node_kind_str == "element":
            yield from iter_elements(child, name, local_name=local_name)


def attributes(node: PyXdmNode) -> dict[str, str]:
    """Return element attributes keyed by readable local name."""

    return {
        display_name(attribute.name): attribute.string_value
        for attribute in node.attributes
    }


def attribute_value(
    node: PyXdmNode,
    name: str,
    default: str | None = None,
) -> str | None:
    """Return one attribute value by name."""

    value = node.get_attribute_value(saxon_qname(name))
    return default if value is None else value


def normalized_text(node: PyXdmNode) -> str:
    """Return whitespace-normalized descendant text for *node*."""

    return " ".join(node.string_value.split())


def select_nodes(
    proc: PySaxonProcessor,
    context: PyXdmNode,
    xpath: str,
    *,
    namespaces: dict[str, str] | None = None,
) -> list[PyXdmNode]:
    """Evaluate XPath and return the resulting nodes as a list."""

    xpath_proc = proc.new_xpath_processor()
    for prefix, uri in (namespaces or {}).items():
        xpath_proc.declare_namespace(prefix, uri)
    xpath_proc.set_context(xdm_item=context)
    result = xpath_proc.evaluate(xpath)
    return [] if result is None else list(result)


def select_first(
    proc: PySaxonProcessor,
    context: PyXdmNode,
    xpath: str,
    *,
    namespaces: dict[str, str] | None = None,
) -> PyXdmNode | None:
    """Evaluate XPath and return the first item, if any."""

    xpath_proc = proc.new_xpath_processor()
    for prefix, uri in (namespaces or {}).items():
        xpath_proc.declare_namespace(prefix, uri)
    xpath_proc.set_context(xdm_item=context)
    return xpath_proc.evaluate_single(xpath)


def first_string(
    proc: PySaxonProcessor,
    context: PyXdmNode,
    xpath: str,
    *,
    namespaces: dict[str, str] | None = None,
) -> str | None:
    """Evaluate XPath and return the first item's non-empty string value."""

    result = select_first(proc, context, xpath, namespaces=namespaces)
    if result is None:
        return None
    value = result.string_value
    return value if value != "" else None


def xpath_boolean(
    proc: PySaxonProcessor,
    context: PyXdmNode,
    xpath: str,
    *,
    namespaces: dict[str, str] | None = None,
) -> bool:
    """Evaluate XPath using XPath effective boolean value rules."""

    xpath_proc = proc.new_xpath_processor()
    for prefix, uri in (namespaces or {}).items():
        xpath_proc.declare_namespace(prefix, uri)
    xpath_proc.set_context(xdm_item=context)
    return xpath_proc.effective_boolean_value(xpath)


def serialize_node(
    proc: PySaxonProcessor,
    node: PyXdmNode,
    *,
    remove_namespaces: bool = False,
) -> str:
    """Serialize *node* with SaxonC."""

    if remove_namespaces:
        xslt_proc = proc.new_xslt30_processor()
        stylesheet = xslt_proc.compile_stylesheet(
            stylesheet_text=_STRIP_NAMESPACES_STYLESHEET
        )
        return stylesheet.transform_to_string(xdm_node=node)
    return first_string(proc, node, "serialize(.)") or ""
