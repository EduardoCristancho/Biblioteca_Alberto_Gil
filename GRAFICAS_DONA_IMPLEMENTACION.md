# Implementación de Gráficas de Dona Dinámicas - CSS Puro + Django

## Descripción Técnica

Esta implementación agrega gráficas de dona dinámicas al dashboard del sistema de biblioteca usando únicamente CSS puro (conic-gradient) y Django, sin JavaScript ni librerías externas.

## Componentes Implementados

### 1. Backend - Cálculo de Porcentajes (views.py)

Se agregaron cálculos de porcentajes en la vista `dashboard_page()`:

- **Títulos Únicos**: Porcentaje de documentos disponibles vs agotados vs sin ejemplares
- **Préstamos Activos**: Porcentaje de préstamos al día vs vencidos
- **Préstamos Vencidos**: Distribución por urgencia (1-7 días, 8-30 días, +30 días)

### 2. Conversión de Porcentajes a Grados

Se utiliza el filtro nativo de Django `widthratio` para convertir porcentajes (0-100%) a grados (0-360°):
```django
{% widthratio porcentaje 100 360 %}
```

### 3. Estilos CSS (style.css)

#### Estructura de la Gráfica de Dona:
```css
.donut-chart {
    /* Contenedor principal */
}

.donut-chart-ring {
    /* Anillo con conic-gradient dinámico */
    background: conic-gradient(
        var(--segment-1-color) 0deg var(--segment-1-end),
        var(--segment-2-color) var(--segment-1-end) var(--segment-2-end),
        var(--segment-3-color) var(--segment-2-end) 360deg
    );
    /* Máscara radial para crear el efecto de dona */
    mask: radial-gradient(circle at center, transparent 35%, black 36%);
}

.donut-chart-center {
    /* Círculo central con porcentaje */
}
```

#### Variables CSS Dinámicas:
- `--segment-1-end`: Ángulo final del primer segmento
- `--segment-2-end`: Ángulo final del segundo segmento
- `--segment-1-color`, `--segment-2-color`, `--segment-3-color`: Colores de segmentos

### 4. Template HTML (dashboard.html)

Cada tarjeta del dashboard incluye:
```html
<div class="donut-chart inventory" style="
    --segment-1-end: {% widthratio titulos_disponibles_pct|default:0 100 360 %}deg;
    --segment-2-end: {% widthratio titulos_disponibles_pct|default:0|add:titulos_agotados_pct|default:0 100 360 %}deg;
">
    <div class="donut-chart-ring"></div>
    <div class="donut-chart-center">
        {{ titulos_disponibles_pct|default:0 }}%
    </div>
</div>
```

## Tipos de Gráficas Implementadas

### 1. Inventario (Títulos Únicos)
- **Verde**: Documentos con stock disponible
- **Naranja**: Documentos agotados (sin stock)
- **Gris**: Documentos sin ejemplares físicos

### 2. Préstamos Activos
- **Verde**: Préstamos al día
- **Rojo**: Préstamos vencidos

### 3. Préstamos Vencidos (Por Urgencia)
- **Rojo**: Más de 30 días vencidos (crítico)
- **Naranja**: 8-30 días vencidos (moderado)
- **Amarillo**: 1-7 días vencidos (reciente)

## Características Técnicas

### ✅ Ventajas de esta Implementación:
- **Sin JavaScript**: Renderizado completamente del lado del servidor
- **Dinámico**: Los datos se actualizan automáticamente con cada carga
- **Responsivo**: Se adapta a diferentes tamaños de pantalla
- **Performante**: CSS puro es más rápido que librerías JS
- **Mantenible**: Lógica centralizada en Django
- **Nativo**: Usa filtros integrados de Django (`widthratio`)

### 🎨 Efectos Visuales:
- Transición suave en hover (scale 1.05)
- Sombra en el círculo central
- Colores consistentes con la paleta del sistema
- Leyendas descriptivas con puntos de color

### 📱 Responsividad:
- Gráficas más pequeñas en móviles (60px vs 80px)
- Texto de leyenda ajustado para pantallas pequeñas

## Uso y Mantenimiento

### Para Agregar Nuevas Gráficas:
1. Calcular porcentajes en `dashboard_page()` (views.py)
2. Pasar datos en el contexto
3. Agregar HTML con variables CSS dinámicas usando `widthratio`
4. Definir colores en CSS si es necesario

### Para Modificar Colores:
Editar las variables CSS en `.donut-chart.tipo`:
```css
.donut-chart.nuevo-tipo {
    --segment-1-color: #color1;
    --segment-2-color: #color2;
    --segment-3-color: #color3;
}
```

## Compatibilidad

- ✅ Chrome/Edge (soporte completo para conic-gradient)
- ✅ Firefox (soporte completo)
- ✅ Safari (soporte completo)
- ⚠️ IE11 (no soporta conic-gradient, fallback a colores sólidos)

Esta implementación cumple con todos los requisitos: es purista (sin JS), dinámica, visualmente atractiva y completamente integrada con Django usando filtros nativos.