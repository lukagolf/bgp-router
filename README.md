# BGP Router

## High Level Overview
For each type of BGP message, I introduced a separate helper function to process that message. Additionally, I added some properties/class variables to store the update messages received by the router and a table to track all the routes known to the router.

I'm consistently checking if any sockets have a message using `select()`. Upon receiving messages, they're passed to the `handle_msg()` function, which then dispatches the appropriate helper function.

## Challenges Faced
One challenge I encountered was handling binary numbers in Python. Since Python lacks a distinct data type for binary numbers, I had to use strings. This led me to create functions to convert IP addresses to a standard binary string representation, which became essential in various parts of the program.

Another challenge was understanding the inner workings of the router. To address this, I heavily relied on print debugging to gain insights into the router's activities. More details on this are available in the "How I Tested" section.

Grasping networks and subnetting concepts was another significant hurdle. I spent considerable time re-reading project guidelines and in-class notes to ensure the router adhered to the specifications.

## Good Features
A notable feature of the program is its encapsulation within the router class, making the code more manageable and eliminating the need for global variables. My approach to message handling, where I designated separate handlers for different message types, ensured clarity and better manageability. Another advantage is the consistent binary number representation. Given Python's absence of a built-in type for bytes, I devised a technique to convert IP addresses (or a tuple of 8 octets) into corresponding binary numbers, proving invaluable for applying netmasks to network addresses.

## How I Tested
Testing involved the supplied config files. Initially, after making code modifications, I would run beginner tests manually. However, as my code began passing more tests, I primarily relied on the `test` script. Print debugging was indispensable, offering a peek into the router's state. Relying solely on the output from test scripts was challenging, so my print statements greatly aided in ensuring the router tables were accurately modified by the helper functions.