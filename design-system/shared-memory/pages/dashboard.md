# Dashboard visual override

This page-level specification overrides the generated master style for the authenticated dashboard and login screen.

## Direction

- Product metaphor: a live neural operations console for shared agent memory.
- Style: dark technical interface, restrained glass surfaces, Bento metrics, visible network topology and subtle grid depth.
- Visual complexity comes from hierarchy, layered surfaces and data relationships. Keep controls familiar and readable.
- Use only Lucide outline icons. Decorative icons are hidden from assistive technology.

## Color tokens

| Role           | Value                       |
| -------------- | --------------------------- |
| Canvas         | `#070b14`                   |
| Surface        | `rgba(15, 23, 39, 0.86)`    |
| Raised surface | `#131e32`                   |
| Primary text   | `#f3f7ff`                   |
| Muted text     | `#93a4bb`                   |
| Accent         | `#2ee6a6`                   |
| Accent strong  | `#18be88`                   |
| Blue signal    | `#83b7ff`                   |
| Violet signal  | `#a78bfa`                   |
| Border         | `rgba(148, 163, 184, 0.15)` |
| Focus          | `#5eead4`                   |

## Components

- Cards use 16–20px radii, a one-pixel translucent border and subtle inner highlight.
- Primary actions use a mint gradient with dark foreground and a visible focus ring.
- Navigation selection combines text, icon, surface and a glowing edge marker so state never depends on color alone.
- Status chips use text and an icon or dot. A dot is always paired with a readable label.
- Forms retain visible labels, helper text, paste support and native controls.
- Dialogs use the native `dialog` element and a strong scrim.

## Motion

- Use 180–220ms transitions for controls and cards.
- Metric cards may enter with a short 55ms stagger.
- Do not animate layout dimensions.
- Disable nonessential motion under `prefers-reduced-motion: reduce`.

## Responsive behavior

- Desktop sidebar: 272px; compact desktop: 238px.
- Below 850px, navigation becomes an off-canvas drawer.
- Below 600px, cards collapse to one column where needed and decorative network visuals simplify.
- Validate at 375px, 768px, 1024px and 1440px with no horizontal overflow.

## Accessibility

- Maintain 4.5:1 contrast for normal text and 3:1 for control boundaries.
- Interactive targets are at least 44px high.
- Keep the skip link and visible three-pixel focus treatment.
- Preserve logical DOM and tab order in both RTL and LTR layouts.
