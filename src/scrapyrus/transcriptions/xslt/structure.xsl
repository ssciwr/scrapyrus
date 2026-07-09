<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet
    version="3.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    exclude-result-prefixes="#all">

  <xsl:mode name="plain-text" on-no-match="shallow-skip"/>

  <xsl:template match="*" mode="plain-text">
    <xsl:apply-templates mode="plain-text"/>
  </xsl:template>

  <xsl:template match="text()[normalize-space()]" mode="plain-text">
    <xsl:value-of select="replace(., '\s+', ' ')"/>
  </xsl:template>

  <xsl:template match="text()" mode="plain-text">
    <xsl:if test="not(contains(., '&#xA;') or contains(., '&#xD;'))">
      <xsl:text> </xsl:text>
    </xsl:if>
  </xsl:template>

  <xsl:template match="*:lb" mode="plain-text">
    <xsl:if test="preceding::*[local-name() = 'lb']">
      <xsl:text>&#xA;</xsl:text>
    </xsl:if>
  </xsl:template>

  <xsl:template match="*:teiHeader | *:head | *:note | *:certainty" mode="plain-text"/>
  <xsl:template match="*:gap" mode="plain-text">
    <xsl:if test="$break_on_gap">
      <xsl:text>&#xA;</xsl:text>
    </xsl:if>
  </xsl:template>

  <xsl:template match="*:milestone | *:fw" mode="plain-text"/>

  <xsl:template match="*:space" mode="plain-text">
    <xsl:text> </xsl:text>
  </xsl:template>
</xsl:stylesheet>
