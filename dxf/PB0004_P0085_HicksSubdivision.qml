<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34.4-Prizren" styleCategories="Symbology|Labeling" labelsEnabled="1">
  <renderer-v2 type="embeddedSymbol" forceraster="0" enableorderby="0" symbollevels="0">
    <symbols>
      <symbol alpha="1" name="0" type="line" clip_to_extent="1" force_rhr="0">
        <layer enabled="1" locked="0" pass="0" class="SimpleLine">
          <Option type="Map">
            <Option value="0" name="align_dash_pattern" type="QString"/>
            <Option value="square" name="capstyle" type="QString"/>
            <Option value="0.35" name="line_width" type="QString"/>
            <Option value="MM" name="line_width_unit" type="QString"/>
          </Option>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
  <labeling type="simple">
    <settings calloutType="simple">
      <text-style fontFamily="Open Sans" fontSize="6.0" fontSizeUnit="Point" textColor="0,0,0,255" isExpression="0" fieldName="Text" blendMode="0">
        <text-buffer bufferDraw="1" bufferSize="0.6" bufferSizeUnits="Point" bufferColor="255,255,255,255" bufferOpacity="1"/>
      </text-style>
      <placement placement="0" dist="0" priority="5" preserveRotation="1"/>
      <rendering scaleMin="0" scaleMax="0" obstacle="0" displayAll="0"/>
      <dd_properties>
        <Option type="Map">
          <Option value="" type="QString" name="name"/>
          <Option type="Map" name="properties">
            <Option type="Map" name="LabelRotation">
              <Option value="true" type="bool" name="active"/>
              <Option value="CASE WHEN &quot;Linetype&quot; LIKE 'ROT_%' THEN -to_real(substr(&quot;Linetype&quot;, 5)) ELSE 0.0 END" type="QString" name="expression"/>
              <Option value="3" type="int" name="type"/>
            </Option>
            <Option type="Map" name="Size">
              <Option value="true" type="bool" name="active"/>
              <Option value="CASE WHEN &quot;Layer&quot; = 'TABLE_TEXT' THEN 4.2 WHEN &quot;Layer&quot; = 'TABLE_HEADER' THEN 5.2 WHEN &quot;Layer&quot; = 'TITLEBLOCK' THEN 7.0 WHEN &quot;Layer&quot; = 'TEXT-LABELS' THEN 5.0 ELSE 5.5 END" type="QString" name="expression"/>
              <Option value="3" type="int" name="type"/>
            </Option>
          </Option>
          <Option value="collection" type="QString" name="type"/>
        </Option>
      </dd_properties>
    </settings>
  </labeling>
</qgis>
