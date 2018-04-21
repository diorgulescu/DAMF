# Device Management Framework

## Purpose ##
These is a framework providing embedded device lab management. 
It is aimed at embedded software developers, software testers and lab admins and it strives to provide
a unified way of working with the boards available for automated testing.

For now, this is UNIX-compatible only.

To put it more simply, this can also be used in embedded test automation contexts. Every embedded software company has some sort of an internal lab. This framework is aimed to become the layer between the company's lab and the test automation team. By providing simple ways to deal with hardware devices, the test automation engineers can focus on how to write better tests, leaving all the board/device management and interaction work to the framework.

## Current status ##

This software is still "work in progress" and small parts of the current code are forked from a framework I wrote for a specific context & customer. 
The ResourcePool component is momentarily a stub, since this module has to be written and adapted to a more general use (the original version uses some dedicated tools that were available in the customers environment), maybe using pdu-client.
All other developments are totally independent of previous implementations.

A web server component will be added shortly.

## Goals ##
In the end, this framework will provide:
- a test job scheduling mechanism (using queues)
- a daemon service that receives requests
- a concise web interface for browsing test results, test run statuses & the such (somewhere down the line...) 

Complete design & implementation diagrams and mindmaps, along with module documentation, can and will be found in the "docs" folder.