# Run your Astro code without a webserver

I needed to run some astro code on a clients machine where nothing can be installed.  
I choose Astro to export a static site but it still needs a webserver to serve the source files

I came across https://github.com/ixkaito/astro-relative-links so now css files are loaded properly and I can navigate around on my pages

Astro JS was also no problem but I used a React UI library that required island interactivity.
Whenever Astro tries to load a js file it will run into a cors error.

This little script solves the problem
- It iterates over all the html files in your distribution directory, detects which framework renderers and components are used
- It embedds them and their dependencies directly in the html page instead of seperate js files
- It overrides all imports and exports so they are assigned and loaded from a global window variable
- All dependencies are awaited with Timeouts.
- The render code is modified to load the correct files from the urls instead of dynamically importing them and causing cors errors
- Once everything has been loaded the renderer will execute and hydrate all your components
