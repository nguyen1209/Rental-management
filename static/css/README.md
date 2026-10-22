# CSS structure

- `style.css`: shared base styles and admin layout.
- `customer/`: storefront, cart, account, rental and product page styles.
- `admin/`: admin-only components and tools.
- `shared/`: typography and flash notifications used in more than one area.

CSS is loaded from `templates/base.html` in cascade order. Keep the current order when adding or moving stylesheets. The admin login page loads the shared flash stylesheet directly.
