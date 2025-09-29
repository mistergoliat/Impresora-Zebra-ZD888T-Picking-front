from jinja2 import Template

ZPL_TEMPLATE = Template(
    """^XA
^CI28
^PW240
^LL400
^FO10,10^A0N,26,26^FD{{ item_name }}^FS
^FO10,50^A0N,24,24^FDSKU: {{ item_code }}^FS
^FO10,90^BCN,80,Y,N,N^FD{{ item_code }}^FS
^FO10,190^A0N,22,22^FDFECHA: {{ fecha_ingreso }}^FS
^XZ"""
)


def render_product_label(item_code: str, item_name: str, fecha_ingreso: str) -> str:
    return ZPL_TEMPLATE.render(
        item_code=item_code,
        item_name=item_name,
        fecha_ingreso=fecha_ingreso,
    )
