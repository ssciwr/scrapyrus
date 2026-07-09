<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet
    version="3.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    exclude-result-prefixes="#all">

  <xsl:template match="*:choice" mode="plain-text">
    <xsl:choose>
      <xsl:when test="$regularize and *[local-name() = 'reg']">
        <xsl:apply-templates select="*[local-name() = 'reg'][1]/node()" mode="plain-text"/>
      </xsl:when>
      <xsl:when test="*[local-name() = 'orig']">
        <xsl:apply-templates select="*[local-name() = 'orig'][1]/node()" mode="plain-text"/>
      </xsl:when>
      <xsl:when test="$regularize and *[local-name() = 'corr']">
        <xsl:apply-templates select="*[local-name() = 'corr'][1]/node()" mode="plain-text"/>
      </xsl:when>
      <xsl:when test="*[local-name() = 'sic']">
        <xsl:apply-templates select="*[local-name() = 'sic'][1]/node()" mode="plain-text"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:apply-templates mode="plain-text"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template match="*:app" mode="plain-text">
    <xsl:choose>
      <xsl:when test="*[local-name() = 'lem']">
        <xsl:apply-templates select="*[local-name() = 'lem'][1]/node()" mode="plain-text"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:apply-templates select="node()[1]" mode="plain-text"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template match="*:subst" mode="plain-text">
    <xsl:choose>
      <xsl:when test="*[local-name() = 'add']">
        <xsl:apply-templates select="*[local-name() = 'add'][1]/node()" mode="plain-text"/>
      </xsl:when>
      <xsl:otherwise>
        <xsl:apply-templates mode="plain-text"/>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template match="*:subst/*[local-name() = 'del']" mode="plain-text"/>
</xsl:stylesheet>
