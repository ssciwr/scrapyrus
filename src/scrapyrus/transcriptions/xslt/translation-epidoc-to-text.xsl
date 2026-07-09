<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet
    version="3.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:s="urn:scrapyrus:transcriptions"
    exclude-result-prefixes="#all">

  <xsl:include href="structure.xsl"/>
  <xsl:include href="choices.xsl"/>

  <xsl:output method="text" encoding="UTF-8"/>

  <xsl:param name="language" as="xs:string?" select="()"/>
  <xsl:param name="break_on_gap" as="xs:boolean" select="false()"/>
  <xsl:param name="regularize" as="xs:boolean" select="false()"/>

  <xsl:template match="/">
    <xsl:variable name="translations"
        select=".//*[local-name() = 'div'][@type = 'translation']
                  [not(ancestor::*[local-name() = 'div'][@type = 'translation'])]"/>
    <xsl:variable name="selected-translations"
        select="if (exists($language))
                then $translations[
                  @*[local-name() = 'lang'
                     and namespace-uri() =
                       'http://www.w3.org/XML/1998/namespace'] = $language
                ]
                else $translations"/>
    <xsl:variable name="raw">
      <xsl:choose>
        <xsl:when test="exists($translations)">
          <xsl:for-each select="$selected-translations">
            <xsl:if test="position() gt 1">
              <xsl:text>&#xA;</xsl:text>
            </xsl:if>
            <xsl:apply-templates select="." mode="plain-text"/>
          </xsl:for-each>
        </xsl:when>
        <xsl:otherwise>
          <xsl:apply-templates select="/*" mode="plain-text"/>
        </xsl:otherwise>
      </xsl:choose>
    </xsl:variable>
    <xsl:value-of select="s:clean-text(string($raw))"/>
  </xsl:template>

  <xsl:template match="*:p" mode="plain-text">
    <xsl:apply-templates mode="plain-text"/>
    <xsl:text>&#xA;</xsl:text>
  </xsl:template>

  <xsl:template match="*:milestone" mode="plain-text" priority="1">
    <xsl:choose>
      <xsl:when test="@rend = ('break', 'horizontal-rule')">
        <xsl:text>&#xA;</xsl:text>
      </xsl:when>
      <xsl:when test="@unit = 'line'">
        <xsl:text> </xsl:text>
      </xsl:when>
    </xsl:choose>
  </xsl:template>

  <xsl:function name="s:clean-text" as="xs:string">
    <xsl:param name="text" as="xs:string"/>
    <xsl:variable name="newlines" select="replace($text, '&#xD;&#xA;?', '&#xA;')"/>
    <xsl:variable name="clean-lines" as="xs:string*">
      <xsl:for-each select="tokenize($newlines, '&#xA;')">
        <xsl:sequence select="normalize-space(.)"/>
      </xsl:for-each>
    </xsl:variable>
    <xsl:sequence
        select="replace(replace(string-join($clean-lines, '&#xA;'), '^[\s]+', ''), '[\s]+$', '')"/>
  </xsl:function>
</xsl:stylesheet>
