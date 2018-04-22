# Device Automation & Management Framework

## Purpose ##
This framework is aimed at embedded software developers, software testers and lab admins and it strives to provide a unified way of working with the boards available for automated testing. 
From board lab management tasks to board access provisioning (by viewing each board/device as a resource that can be dinamically allocated from a pool of resources) and test automation, this project is meant to fill a software solution gap that I noticed over the past couple of years.

Every embedded software company has some sort of an internal lab. Interacting with it in an efficient manner involves quite a lot of administration work. Apart from setting everything up and connecting bits & wires, a way of accessing the lab must be provided. In almost all cases, each team/company ends up writing an in-house solution from scratch (which may bring benefits on the short term, but it does so happen that future features and issues are not taken into account due to lack o expertise), and when several companies (or teams within the same company) end up writing their own software for doing the exact same thing, clearly something is wrong.

This framework is aimed at becoming that layer between the company's lab and the test automation team. By providing simple ways to deal with hardware devices, the test automation engineers can focus on how to write better tests, leaving all the board/device management and interaction work to the framework. Also, lab admins can use this for management tasks, given the fact that DAMF offers a quite easy manner of adding new devices to the resource pool.

## Current status ##

_For now, this is UNIX-compatible only._

This software is still "work in progress" and small parts of the current code are forked from a framework I wrote for a specific context & customer. There are a lot of things to be done and I would be more than glad if other people in the industry would jump in with ideas and code work.

The ResourcePool component is momentarily a stub, since this module has to be written and adapted to a more general use (the original version uses some dedicated tools that were available in the customers environment), maybe using pdu-client.
All other developments are totally independent of previous implementations.

A web server component will be added shortly.

## Goals ##
In the end, this framework will provide:
- a test job scheduling mechanism (using queues)
- a daemon service that receives requests
- a concise web interface for browsing test results, test run statuses & the such (somewhere down the line...)
- user-based access (with access rights management, customizations, etc.)


Complete design & implementation diagrams and mindmaps, along with module documentation, can and will be found in the "docs" folder.