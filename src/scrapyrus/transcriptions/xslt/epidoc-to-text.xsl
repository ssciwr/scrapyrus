<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet
    version="3.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:s="urn:scrapyrus:transcriptions"
    exclude-result-prefixes="#all">

  <xsl:include href="structure.xsl"/>
  <xsl:include href="expansion.xsl"/>
  <xsl:include href="editorial.xsl"/>
  <xsl:include href="choices.xsl"/>

  <xsl:output method="text" encoding="UTF-8"/>

  <xsl:param name="abbrev" as="xs:boolean" select="false()"/>
  <xsl:param name="break_on_gap" as="xs:boolean" select="false()"/>
  <xsl:param name="lost" as="xs:boolean" select="false()"/>
  <xsl:param name="unclear" as="xs:boolean" select="false()"/>
  <xsl:param name="regularize" as="xs:boolean" select="false()"/>

  <xsl:template match="/">
    <xsl:variable name="edition" select="(.//*[local-name() = 'div'][@type = 'edition'], /*)[1]"/>
    <xsl:variable name="raw">
      <xsl:apply-templates select="$edition" mode="plain-text"/>
    </xsl:variable>
    <xsl:value-of select="s:clean-text(string($raw))"/>
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
