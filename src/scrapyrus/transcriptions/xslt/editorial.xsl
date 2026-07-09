<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet
    version="3.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    exclude-result-prefixes="#all">

  <xsl:template match="*:supplied" mode="plain-text"/>

  <xsl:template match="*:supplied[@reason = 'lost']" mode="plain-text">
    <xsl:if test="$lost">
      <xsl:apply-templates mode="plain-text"/>
    </xsl:if>
  </xsl:template>

  <xsl:template match="*:unclear" mode="plain-text">
    <xsl:if test="$unclear">
      <xsl:apply-templates mode="plain-text"/>
    </xsl:if>
  </xsl:template>
</xsl:stylesheet>
