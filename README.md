# PCBuildMate
Link to live site - https://w########.herokuapp.com/

Project board -  https://github.com/users/Ruon90/projects/13

![Website landing page](/documentation/images/home.png)

## Index
1. [Overview](#overview)
2. [UX Design Process](#ux-design-process)
    - [User Stories](#user-stories)
    - [Wireframes](#wireframes)
    - [Color Scheme](#color-scheme)
    - [Fonts](#fonts)
3. [Features](#features)
4. [Database](#database)
5. [Deployment](#deployment)
6. [Testing and Validation](#testing-and-validation)
7. [AI implementation](#ai-implementation)
8. [Tech used](#tech-used)
9. [Improvements](#improvments-and-future-development)
10. [References](#references)
11. [Learning points](#learning-points)

## Overview


## UX Design Process

### User stories

✅ Must-Have (Critical for MVP)
<details>

    • As a beginner PC builder, I want to input my budget and use case (e.g., gaming, editing, streaming) so that I receive a curated build optimized for performance and value.

    • As a user, I must see benchmark scores and price/performance ratios for each component so I can make informed decisions.

    • As a visitor, I need the site to load quickly and display clearly on both desktop and mobile so I can use it anywhere.

    • As a user, I want affiliate links for each part so I can purchase confidently without searching elsewhere.
    • As a global user, I must be able to view prices and availability based on my region.

    • As a registered user, I must be able to save builds, update/edit saved builds, and delete builds from my profile so I can manage my configurations over time.
</details>
<br>
🤝 Should-Have (Important but not critical)
<details>

    • As a returning user, I want to save and compare multiple builds so I can revisit and refine my choices.

    • As a curious builder, I want to filter builds by brand preference or aesthetic (e.g., RGB, minimalist) to match my style.

    • As a user, I should be able to toggle between light and dark mode for better readability.

    • As a user, I want to see compatibility warnings (e.g., PSU wattage, case fit) so I avoid build errors.
</details>
<br>
💡 Could-Have (Nice to include if time allows)
<details>

    • As a user, I could benefit from a “Build of the Month” feature showcasing top-rated configurations.

    • As a beginner, I could use tooltips or glossary popups explaining technical terms like TDP, VRAM, or PCIe lanes.

    • As a user, I could get notifications when a part in my saved build drops in price.
</details>
<br>

❌ Won’t-Have (Out of scope for now)
<details>

    • As a user, I won’t expect real-time chat support or AI-guided build walkthroughs at launch.

    • As a user, I won’t expect a community forum or discussion board in the initial release.
</details>

### Wireframes

#### Home page
<details>

![home wireframe](/documentation/wireframes/homeWF.png)
</details>

#### Results page
<details>

![moblie wireframe](/documentation/wireframes/resultsWF.png)
</details>

#### Login page
<details>

![moblie wireframe](/documentation/wireframes/loginWF.png)
</details>

### Color scheme
please generate color scheme from the used colours


### Fonts
ibm plex sans for headers

inter for body

chosen by co pilot as a tech orientated professional font
### Mockups


## Features

### data -
- slugify to match benchmarks
- ai enriched for determining factors (msrp etc)
- userbenchmark for gaming benchmarks, blender for workstation
- tech power up for item details

### calculator -

- build calculator logic (compatibility price etc)
- fps logic
- render time logic
- save builds
- edit builds

### Upgrade calculator -

- upgrade logic
- improvement % logic
- fps delta logic
- render time delta logic

### build preview -
- build preview logic
- save
- edit

### Saved builds -
- saved build logic
- preivew logic
- edit logic
- delete logic 
- CRUD functionality


## Database
database explanation, using postgres psycopg2 etc

### ERD
<image>

### Data import
- cover utils to import cleaned and enriched data

## Deployment
- quick guide on how to deploy to heroku from git clone to ide to pushing / deploying
## Testing and validation

## AI implementation

## Improvements
Images for cards

Amazon API

Adsense

improve UX

## References

## Tech used
HTML
CSS
JavaScript
Bootstrap
Python
Django
co-pilot
chat gpt

## Learning points