---
name: Academic Precision
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#44474d'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#75777e'
  outline-variant: '#c5c6ce'
  surface-tint: '#4f5e7e'
  primary: '#041632'
  on-primary: '#ffffff'
  primary-container: '#1b2b48'
  on-primary-container: '#8393b5'
  inverse-primary: '#b7c7eb'
  secondary: '#5a5f62'
  on-secondary: '#ffffff'
  secondary-container: '#dce0e4'
  on-secondary-container: '#5e6367'
  tertiary: '#001d03'
  on-tertiary: '#ffffff'
  tertiary-container: '#003408'
  on-tertiary-container: '#55a454'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d7e2ff'
  primary-fixed-dim: '#b7c7eb'
  on-primary-fixed: '#091b37'
  on-primary-fixed-variant: '#374765'
  secondary-fixed: '#dfe3e7'
  secondary-fixed-dim: '#c3c7cb'
  on-secondary-fixed: '#171c1f'
  on-secondary-fixed-variant: '#43474b'
  tertiary-fixed: '#a3f69c'
  tertiary-fixed-dim: '#88d982'
  on-tertiary-fixed: '#002204'
  on-tertiary-fixed-variant: '#005312'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  gutter: 16px
  margin-mobile: 16px
  margin-desktop: 32px
  max-width: 1280px
---

## Brand & Style

The design system is engineered for high-stakes exam preparation, blending the rigor of a classical academic institution with the efficiency of a modern productivity suite. The brand personality is authoritative, reliable, and results-oriented. It targets serious students and educators who require a distraction-free environment to analyze performance metrics and track syllabus progress.

The design style is **Minimalist-Functional with a Corporate-Modern backbone**. It prioritizes information density and clarity over decorative elements. By utilizing sharp edges and a restricted color palette, the UI communicates a sense of precision and "digital coaching." Every visual element must serve a functional purpose, facilitating a state of "deep work" and data comprehension.

## Colors

The color strategy uses "Deep Navy" as the anchor to establish authority and trust. The palette is intentionally high-contrast to ensure that data points and status indicators remain the focal point of the experience.

- **Primary (Deep Navy):** Used for navigation, primary headers, and critical call-to-action buttons. It represents the "Coach" persona.
- **Secondary (Slate Tint):** A cool neutral used for background sections, borders, and disabled states to maintain a clean, organized structure.
- **Status Accents:** These are strictly reserved for performance feedback. 
    - **Success Green:** Indicates mastery of a topic or goal completion.
    - **Warning Amber:** Highlights areas needing review or stagnant progress.
    - **Urgent Red:** Flags missed deadlines or critical score drops.
- **Background:** Pure white is used for content areas to maximize legibility and provide an "open-book" feel.

## Typography

The typography system relies on **Inter** for its neutral, highly legible character, making it ideal for long-form reading and complex dashboard views. To emphasize the "data-driven" aspect of the system, **JetBrains Mono** is introduced for labels, numerical data, and meta-info, providing a technical, precise aesthetic.

- **Headlines:** Use tight letter spacing and semi-bold weights to create a strong visual hierarchy.
- **Body Text:** Standardized on a 16px grid to ensure comfort during study sessions.
- **Data Labels:** Always set in Monospace to ensure numerical alignment in tables and progress trackers.
- **Hierarchy:** Use color (Primary Navy for titles, Neutral Slate for secondary info) rather than just size to distinguish between content types.

## Layout & Spacing

This design system employs a **Fixed Grid** model for desktop to maintain a structured, document-like feel, while transitioning to a fluid model for mobile.

- **Grid:** A 12-column grid system is used for dashboards. Spacing is strictly based on a **4px baseline grid** to reinforce the "Precision" theme.
- **Padding:** Content containers use generous internal padding (24px or 32px) to prevent data density from feeling overwhelming.
- **Breakpoints:**
  - **Mobile (<768px):** Single column, 16px side margins.
  - **Tablet (768px - 1024px):** 8-column grid, sidebar collapses to an icon-only rail.
  - **Desktop (>1024px):** 12-column grid, max content width of 1280px, centered.

## Elevation & Depth

To maintain the minimalist and professional tone, this design system avoids traditional shadows. Instead, it uses **Tonal Layers** and **Refined Outlines** to communicate hierarchy.

- **Low-Contrast Outlines:** Surfaces are separated by 1px solid borders in a light grey (`#E2E8F0`). 
- **Z-Axis Hierarchy:** 
  - **Level 0 (Background):** White (#FFFFFF).
  - **Level 1 (Cards/Sections):** White with 1px border.
  - **Level 2 (Modals/Popovers):** White with a 1px border in Primary Navy and a very subtle, sharp 4px hard shadow (no blur) to mimic architectural blueprints.
- **Interaction:** On hover, interactive elements should shift background color slightly to Secondary Slate rather than lifting off the page.

## Shapes

The shape language is defined by **mathematical "Soft" precision**. Elements utilize a consistent **4px radius** (`rounded-sm`), which is just enough to prevent the UI from feeling hostile while maintaining a sharp, professional edge.

- **Buttons & Inputs:** Strictly 4px corners.
- **Progress Bars:** Flat ends (0px) to represent "filling a container" or very subtle 2px rounding.
- **Data Containers:** 4px corners with 1px stroke. No pill-shaped elements should be used, as they conflict with the "Academic Excellence" narrative.

## Components

### Buttons
- **Primary:** Deep Navy background, White text, 4px radius. High-contrast.
- **Secondary:** White background, 1px Navy border, Navy text.
- **Ghost:** No background or border, Navy text. Used for secondary actions in tables.

### Progress Tracking
- **Progress Bars:** Use a thick 8px track. The unfilled portion is Light Slate; the filled portion uses the Status Colors (Green/Amber/Red) based on the current score percentage.
- **Circular Gauges:** Used for "Overall Readiness" scores, utilizing a non-rounded, segmented stroke to feel like a technical instrument.

### Input Fields & Structured Forms
- Inputs must have a persistent 1px border. On focus, the border weight increases to 2px in Primary Navy.
- Labels are always positioned above the input field, using the `label-md` (Monospace) font style.

### Cards
- Cards are the primary container for data modules. They feature a 1px `#E2E8F0` border and no shadow. 
- Header areas within cards should have a subtle Light Slate background (`#F8FAFC`) to separate the "Title" from the "Data."

### Status Chips
- Small, rectangular tags with 2px radius. Use a light tinted background of the status color with high-contrast dark text (e.g., Light Green background with Dark Green text).

### Performance Tables
- Use a strictly horizontal-row-only border style. Typography inside tables should use the Monospace font for all numeric values to ensure decimal alignment.