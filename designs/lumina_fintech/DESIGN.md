---
name: Lumina Fintech
colors:
  surface: '#131313'
  surface-dim: '#131313'
  surface-bright: '#393939'
  surface-container-lowest: '#0e0e0e'
  surface-container-low: '#1c1b1b'
  surface-container: '#201f1f'
  surface-container-high: '#2a2a2a'
  surface-container-highest: '#353534'
  on-surface: '#e5e2e1'
  on-surface-variant: '#cbc3d7'
  inverse-surface: '#e5e2e1'
  inverse-on-surface: '#313030'
  outline: '#958ea0'
  outline-variant: '#494454'
  surface-tint: '#d0bcff'
  primary: '#d0bcff'
  on-primary: '#3c0091'
  primary-container: '#a078ff'
  on-primary-container: '#340080'
  inverse-primary: '#6d3bd7'
  secondary: '#adc6ff'
  on-secondary: '#002e6a'
  secondary-container: '#0566d9'
  on-secondary-container: '#e6ecff'
  tertiary: '#4edea3'
  on-tertiary: '#003824'
  tertiary-container: '#00a572'
  on-tertiary-container: '#00311f'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#e9ddff'
  primary-fixed-dim: '#d0bcff'
  on-primary-fixed: '#23005c'
  on-primary-fixed-variant: '#5516be'
  secondary-fixed: '#d8e2ff'
  secondary-fixed-dim: '#adc6ff'
  on-secondary-fixed: '#001a42'
  on-secondary-fixed-variant: '#004395'
  tertiary-fixed: '#6ffbbe'
  tertiary-fixed-dim: '#4edea3'
  on-tertiary-fixed: '#002113'
  on-tertiary-fixed-variant: '#005236'
  background: '#131313'
  on-background: '#e5e2e1'
  surface-variant: '#353534'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  display-lg-mobile:
    fontFamily: Inter
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 30px
    fontWeight: '600'
    lineHeight: 38px
    letterSpacing: -0.01em
  headline-md-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  title-lg:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
  mono-data:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  container-max: 1280px
  gutter: 24px
  margin-desktop: 40px
  margin-mobile: 20px
  stack-xs: 4px
  stack-sm: 8px
  stack-md: 16px
  stack-lg: 24px
  stack-xl: 48px
---

## Brand & Style
The design system is engineered for a premium fintech SaaS environment, prioritizing high-end utility with a sophisticated "Dark Mode First" aesthetic. The brand personality is authoritative yet visionary, evoking a sense of security and cutting-edge performance. 

The visual style blends **Minimalism** with **Glassmorphism**. It utilizes a deep black foundation to create infinite depth, allowing high-contrast typography and vibrant neon accents to guide the user's focus. The emotional response should be one of "effortless control"—where complex financial data feels breathable, spacious, and immediate.

## Colors
The palette is rooted in a "True Black" (#000000) background to maximize OLED efficiency and visual depth. 
- **Primary & Secondary:** Electric Violet and Electric Blue are used sparingly for interactive elements, data visualization, and brand moments.
- **Surface Palette:** Layers are constructed using Deep Charcoal (#121212) and semi-transparent overlays to distinguish between the background and interactive containers.
- **Semantic Text:** High-contrast White (#FFFFFF) is reserved for primary headings and critical data. Muted Gray (#94A3B8) is used for secondary labels and metadata to maintain a clear information hierarchy.
- **Success/Alert:** A vibrant Emerald (#10B981) is introduced for positive financial trends and "success" states.

## Typography
This design system utilizes **Inter** for its exceptional legibility in data-heavy interfaces. Headlines are set with tight letter-spacing and bold weights to ground the layout. For currency, transaction IDs, and developer-facing data, **Geist** is utilized to provide a technical, precise feel. 

Large display sizes are reserved for account balances and hero metrics. All secondary labels use a slightly wider letter-spacing and uppercase styling to ensure they remain distinct from body copy at small sizes.

## Layout & Spacing
The layout follows a **Fixed Grid** model on desktop (12 columns) and a **Fluid Grid** on mobile (4 columns). To maintain a premium, spacious feel, the system utilizes a generous 24px gutter and significant vertical margins (stack-xl).

Padding within components should be expansive. Cards and containers use a minimum of 24px internal padding to ensure financial data does not feel cramped. Layouts should prioritize a "center-out" density, where the most critical financial KPIs are given ample white space (or "black space") to breathe.

## Elevation & Depth
Depth is created through **Glassmorphism** and **Tonal Layering** rather than traditional heavy shadows.
- **Level 0 (Background):** Pure #000000.
- **Level 1 (Cards/Sections):** Deep Charcoal #121212 with a 1px semi-transparent border (White at 10% opacity).
- **Level 2 (Modals/Popovers):** Surface color at 60% opacity with a 20px Backdrop Blur. 
- **Shadows:** Use "Ambient Glows" for active states—soft, ultra-diffused shadows tinted with the primary violet or secondary blue (e.g., `0px 10px 40px rgba(139, 92, 246, 0.15)`).

## Shapes
The shape language is defined by oversized, friendly radii that contrast against the technical nature of fintech. 
- **Base Components:** Buttons and inputs use a 0.5rem (8px) radius.
- **Containers:** Dashboard cards, modals, and main content areas use a **24px (rounded-xl)** radius to create a distinct, modern silhouette.
- **Interactive Elements:** Small chips or tags use a fully pill-shaped (3rem) radius to differentiate them from functional inputs.

## Components
- **Buttons:** Primary buttons use a solid Electric Violet fill with white text. Secondary buttons use a ghost style: a 1px border of #FFFFFF at 20% opacity with a subtle glass blur.
- **Cards:** Defined by a 24px border-radius, a #121212 background, and a subtle top-down linear gradient (White at 5% to Transparent).
- **Input Fields:** Backgrounds should be #000000 with a 1px border of #262626. On focus, the border transitions to Electric Blue with a soft outer glow.
- **Chips/Status:** Use low-opacity fills of the semantic color (e.g., Success is 10% Emerald green fill with 100% Emerald green text).
- **Data Tables:** No vertical borders. Use horizontal dividers at 5% white opacity. Header rows use the `label-md` typography style for clarity.
- **Charts:** Use a 2px stroke width for line charts with a gradient "area" fill that fades into the black background.