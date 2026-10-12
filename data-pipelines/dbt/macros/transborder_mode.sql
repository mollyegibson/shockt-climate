{#- TransBorder's mode of transportation (DISAGMOT) by name, per the BTS TransBorder codes document: 1 vessel, 3 air, 4 mail, 5 truck, 6 rail, 7 pipeline, 8 other, 9 foreign trade zone (a customs status, not a mode). Unknown codes are null. -#}
{% macro transborder_mode(code) %}
    case {{ code }}
        when 1 then 'vessel'
        when 3 then 'air'
        when 4 then 'mail'
        when 5 then 'truck'
        when 6 then 'rail'
        when 7 then 'pipeline'
        when 8 then 'other'
        when 9 then 'foreign_trade_zone'
    end
{% endmacro %}
